WITH
  BaseAdmissions AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      pat.gender,
      pat.anchor_age,
      pat.anchor_year,
      pat.dod,
      adm.admittime,
      adm.dischtime,
      adm.deathtime,
      adm.hospital_expire_flag,
      (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    WHERE
      pat.gender = 'M'
      AND pat.anchor_age BETWEEN 30 AND 55
  ),
  FilteredAdmissions AS (
    SELECT
      *
    FROM
      BaseAdmissions
    WHERE
      age_at_admission BETWEEN 39 AND 49
  ),
  DiagnosesFlags AS (
    SELECT
      fa.hadm_id,
      MAX(CASE
        WHEN dx.icd_version = 9 AND dx.icd_code IN ('25010', '25011', '25012', '25013') THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code IN ('E1010', 'E1011', 'E1110', 'E1111', 'E1310', 'E1311') THEN 1
        ELSE 0
      END) AS has_dka,
      MAX(CASE
        WHEN dx.icd_version = 9 AND dx.icd_code LIKE '410%' THEN 1
        WHEN dx.icd_version = 9 AND dx.icd_code = '4275' THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code LIKE 'I21%' THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code = 'I469' THEN 1
        ELSE 0
      END) AS has_cardio_complication,
      MAX(CASE
        WHEN dx.icd_version = 9 AND dx.icd_code LIKE '433%' THEN 1
        WHEN dx.icd_version = 9 AND dx.icd_code LIKE '434%' THEN 1
        WHEN dx.icd_version = 9 AND dx.icd_code = '431' THEN 1
        WHEN dx.icd_version = 9 AND dx.icd_code = '78039' THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code LIKE 'I61%' THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code LIKE 'I63%' THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code LIKE 'R56%' THEN 1
        ELSE 0
      END) AS has_neuro_complication,
      COUNT(CASE
        WHEN dx.icd_version = 9 AND dx.icd_code IN ('99592', '78552', '0389', '4275', '51881', '51882', 'V5811', '78603') THEN 1
        WHEN dx.icd_version = 9 AND dx.icd_code LIKE '410%' THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code IN ('R6881', 'R570', 'R6521', 'A419', 'I469', 'J9600', 'J80', 'Z5111', 'R0603') THEN 1
        WHEN dx.icd_version = 10 AND dx.icd_code LIKE 'I21%' THEN 1
        ELSE NULL
      END) AS num_critical_illnesses
    FROM
      FilteredAdmissions AS fa
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON fa.hadm_id = dx.hadm_id
    GROUP BY
      fa.hadm_id
  ),
  RiskAndOutcome AS (
    SELECT
      fa.hadm_id,
      fa.age_at_admission,
      df.has_dka,
      df.has_cardio_complication,
      df.has_neuro_complication,
      fa.hospital_expire_flag,
      GREATEST(0, DATETIME_DIFF(fa.dischtime, fa.admittime, DAY)) AS los_days,
      CASE
        WHEN fa.hospital_expire_flag = 1 THEN 1
        WHEN fa.dod IS NOT NULL AND DATETIME_DIFF(fa.dod, fa.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS is_dead_30_day,
      LEAST(
        (fa.age_at_admission - 39) * 2
        + LEAST(df.num_critical_illnesses * 10, 50)
        + (df.has_cardio_complication * 20) + (df.has_neuro_complication * 20),
      100) AS risk_score
    FROM
      FilteredAdmissions AS fa
    INNER JOIN
      DiagnosesFlags AS df
      ON fa.hadm_id = df.hadm_id
  ),
  DkaCohortPercentile AS (
    SELECT
      hadm_id,
      age_at_admission,
      PERCENT_RANK() OVER (ORDER BY risk_score) * 100 AS risk_percentile
    FROM
      RiskAndOutcome
    WHERE
      has_dka = 1
  ),
  CohortComparison AS (
    SELECT
      CASE WHEN has_dka = 1 THEN 'DKA Cohort (Male, 39-49)' ELSE 'General Cohort (Male, 39-49)' END AS cohort_group,
      COUNT(hadm_id) AS num_admissions,
      AVG(risk_score) AS mean_risk_score,
      AVG(is_dead_30_day) * 100 AS mortality_rate_30_day,
      AVG(has_cardio_complication) * 100 AS cardio_complication_rate,
      AVG(has_neuro_complication) * 100 AS neuro_complication_rate,
      AVG(CASE WHEN hospital_expire_flag = 0 THEN los_days END) AS mean_survivor_los_days
    FROM
      RiskAndOutcome
    GROUP BY
      cohort_group
  ),
  TargetProfilePercentile AS (
    SELECT
      'Risk Percentile for Matched Profile (Male, 44, DKA)' AS metric,
      AVG(risk_percentile) AS value
    FROM
      DkaCohortPercentile
    WHERE
      age_at_admission = 44
  )
SELECT
  'Cohort Comparison' AS result_type,
  cohort_group AS metric_name,
  'Num Admissions' AS metric_1_name,
  CAST(num_admissions AS STRING) AS metric_1_value,
  'Mean Risk Score' AS metric_2_name,
  CAST(ROUND(mean_risk_score, 2) AS STRING) AS metric_2_value,
  '30d Mortality Rate (%)' AS metric_3_name,
  CAST(ROUND(mortality_rate_30_day, 2) AS STRING) AS metric_3_value,
  'Cardio Complication Rate (%)' AS metric_4_name,
  CAST(ROUND(cardio_complication_rate, 2) AS STRING) AS metric_4_value,
  'Neuro Complication Rate (%)' AS metric_5_name,
  CAST(ROUND(neuro_complication_rate, 2) AS STRING) AS metric_5_value,
  'Mean Survivor LOS (Days)' AS metric_6_name,
  CAST(ROUND(mean_survivor_los_days, 2) AS STRING) AS metric_6_value
FROM
  CohortComparison
UNION ALL
SELECT
  'Profile-Specific Percentile' AS result_type,
  metric AS metric_name,
  'Avg Percentile for 44 y/o' AS metric_1_name,
  CAST(ROUND(value, 2) AS STRING) AS metric_1_value,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM
  TargetProfilePercentile;
