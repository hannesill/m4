WITH
  DiagnosisFlags AS (
    SELECT
      hadm_id,
      MAX(CASE WHEN icd_code LIKE 'N17%' OR icd_code LIKE '584%' THEN 1 ELSE 0 END) AS has_aki,
      MAX(CASE WHEN icd_code = 'J80' OR icd_code = '518.82' THEN 1 ELSE 0 END) AS has_ards,
      MAX(CASE WHEN icd_code IN ('R68.81', 'R57.0', '995.92', '785.52') THEN 1 ELSE 0 END) AS has_multi_organ_failure,
      MAX(CASE WHEN icd_code IN ('R65.21', 'A41.9', '995.92', '038.9') THEN 1 ELSE 0 END) AS has_septic_shock,
      MAX(CASE WHEN icd_code LIKE 'I21%' OR icd_code IN ('I46.9', '427.5') OR icd_code LIKE '410%' THEN 1 ELSE 0 END) AS has_acute_mi_comp,
      MAX(CASE WHEN icd_code IN ('J96.00', 'J80', '518.81', '518.82') THEN 1 ELSE 0 END) AS has_resp_failure,
      MAX(CASE WHEN icd_code IN ('Z51.11', 'R06.03', 'V58.11', '786.03') THEN 1 ELSE 0 END) AS has_crit_illness_flag,
      COUNT(DISTINCT icd_code) AS diagnosis_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  EnrichedAdmissions AS (
    SELECT
      a.hadm_id,
      p.subject_id,
      p.dod,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      COALESCE(df.has_aki, 0) AS has_aki,
      COALESCE(df.has_ards, 0) AS has_ards,
      LEAST(
        100,
        (
          (CASE WHEN COALESCE(df.has_multi_organ_failure, 0) = 1 THEN 30 ELSE 0 END) +
          (CASE WHEN COALESCE(df.has_septic_shock, 0) = 1 THEN 25 ELSE 0 END) +
          (CASE WHEN COALESCE(df.has_acute_mi_comp, 0) = 1 THEN 20 ELSE 0 END) +
          (CASE WHEN COALESCE(df.has_resp_failure, 0) = 1 THEN 15 ELSE 0 END) +
          (CASE WHEN COALESCE(df.has_crit_illness_flag, 0) = 1 THEN 10 ELSE 0 END) +
          COALESCE(df.diagnosis_count, 0)
        )
      ) AS risk_score,
      CASE
        WHEN a.hospital_expire_flag = 1 THEN 1
        WHEN p.dod IS NOT NULL AND DATE_DIFF(p.dod, a.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS is_30_day_mortality,
      CASE
        WHEN a.hospital_expire_flag = 0 THEN DATETIME_DIFF(a.dischtime, a.admittime, DAY)
        ELSE NULL
      END AS survivor_los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    LEFT JOIN
      DiagnosisFlags AS df ON a.hadm_id = df.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 74 AND 84
  ),
  AkiMedianRisk AS (
    SELECT
      APPROX_QUANTILES(risk_score, 100)[OFFSET(50)] AS median_risk
    FROM
      EnrichedAdmissions
    WHERE
      has_aki = 1
  )
SELECT
  'AKI Cohort (Age 74-84, Male)' AS cohort_profile,
  COUNT(*) AS total_admissions,
  FORMAT(
    '%d (%d-%d)',
    APPROX_QUANTILES(risk_score, 100)[OFFSET(50)],
    APPROX_QUANTILES(risk_score, 100)[OFFSET(25)],
    APPROX_QUANTILES(risk_score, 100)[OFFSET(75)]
  ) AS median_risk_score_with_iqr,
  NULL AS risk_percentile_in_general_pop,
  ROUND(AVG(is_30_day_mortality) * 100, 2) AS mortality_rate_30_day_pct,
  NULL AS aki_rate_pct,
  ROUND(AVG(has_ards) * 100, 2) AS ards_rate_pct,
  ROUND(AVG(survivor_los_days), 1) AS avg_survivor_los_days
FROM
  EnrichedAdmissions
WHERE
  has_aki = 1
UNION ALL
SELECT
  'General Inpatient Cohort (Age 74-84, Male)' AS cohort_profile,
  COUNT(*) AS total_admissions,
  NULL AS median_risk_score_with_iqr,
  NULL AS risk_percentile_in_general_pop,
  ROUND(AVG(is_30_day_mortality) * 100, 2) AS mortality_rate_30_day_pct,
  ROUND(AVG(has_aki) * 100, 2) AS aki_rate_pct,
  ROUND(AVG(has_ards) * 100, 2) AS ards_rate_pct,
  ROUND(AVG(survivor_los_days), 1) AS avg_survivor_los_days
FROM
  EnrichedAdmissions
UNION ALL
SELECT
  'Matched Profile: Percentile of Median AKI Risk Score' AS cohort_profile,
  NULL AS total_admissions,
  NULL AS median_risk_score_with_iqr,
  ROUND(
    SAFE_DIVIDE(
      (SELECT COUNTIF(risk_score < (SELECT median_risk FROM AkiMedianRisk)) FROM EnrichedAdmissions),
      (SELECT COUNT(*) FROM EnrichedAdmissions)
    ) * 100,
    1
  ) AS risk_percentile_in_general_pop,
  NULL AS mortality_rate_30_day_pct,
  NULL AS aki_rate_pct,
  NULL AS ards_rate_pct,
  NULL AS avg_survivor_los_days;
