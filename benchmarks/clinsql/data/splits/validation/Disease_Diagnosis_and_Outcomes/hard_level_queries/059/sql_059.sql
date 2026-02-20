WITH
  base_patients AS (
    SELECT
      subject_id,
      anchor_age,
      dod
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients`
    WHERE
      gender = 'M'
      AND anchor_age BETWEEN 59 AND 69
  ),
  admissions_with_outcomes AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      CASE
        WHEN a.hospital_expire_flag = 1 THEN 1
        WHEN p.dod IS NOT NULL AND DATETIME_DIFF(p.dod, a.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS mortality_30day_flag,
      GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN base_patients AS p ON a.subject_id = p.subject_id
    WHERE
      a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
  ),
  admission_diagnoses_features AS (
    SELECT
      d.hadm_id,
      MAX(CASE
        WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 4) IN ('2501') THEN 1
        WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 4) IN ('E101', 'E111', 'E131') THEN 1
        ELSE 0
      END) AS has_dka,
      MAX(CASE
        WHEN d.icd_version = 9 AND d.icd_code = '5849' THEN 1
        WHEN d.icd_version = 10 AND d.icd_code = 'N179' THEN 1
        ELSE 0
      END) AS has_aki,
      MAX(CASE
        WHEN d.icd_version = 9 AND d.icd_code = '51882' THEN 1
        WHEN d.icd_version = 10 AND d.icd_code = 'J80' THEN 1
        ELSE 0
      END) AS has_ards,
      LEAST(100,
        (
          SUM(CASE
            WHEN (d.icd_version = 9 AND d.icd_code IN ('99592', '78552')) OR (d.icd_version = 10 AND d.icd_code IN ('R6521', 'R570')) THEN 3
            WHEN (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4275' OR d.icd_code IN ('51881', '51882'))) OR (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code = 'I469' OR d.icd_code IN ('J9600', 'J80'))) THEN 2
            WHEN (d.icd_version = 9 AND d.icd_code IN ('0389')) OR (d.icd_version = 10 AND d.icd_code IN ('A419', 'R6881')) THEN 1
            ELSE 0
          END) * 2.5
        ) + (COUNT(DISTINCT d.icd_code) * 0.25)
      ) AS risk_score
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    WHERE d.hadm_id IN (SELECT hadm_id FROM admissions_with_outcomes)
    GROUP BY
      d.hadm_id
  ),
  combined_cohort_data AS (
    SELECT
      a.hadm_id,
      a.mortality_30day_flag,
      a.los_days,
      f.has_dka,
      f.has_aki,
      f.has_ards,
      f.risk_score,
      CASE
        WHEN f.has_dka = 1 THEN 'DKA_Cohort'
        ELSE 'General_Cohort'
      END AS cohort_group
    FROM
      admissions_with_outcomes AS a
      INNER JOIN admission_diagnoses_features AS f
      ON a.hadm_id = f.hadm_id
  ),
  dka_cohort_stats AS (
    SELECT
      'DKA_Cohort' AS cohort_name,
      COUNT(hadm_id) AS total_patients,
      AVG(risk_score) AS mean_risk_score,
      AVG(mortality_30day_flag) AS mortality_30day_rate,
      AVG(has_aki) AS aki_rate,
      AVG(has_ards) AS ards_rate,
      AVG(CASE WHEN mortality_30day_flag = 0 THEN los_days ELSE NULL END) AS survivor_los_days
    FROM combined_cohort_data
    WHERE cohort_group = 'DKA_Cohort'
  ),
  general_cohort_stats AS (
    SELECT
      'General_Cohort' AS cohort_name,
      COUNT(hadm_id) AS total_patients,
      AVG(has_aki) AS aki_rate,
      AVG(has_ards) AS ards_rate,
      AVG(CASE WHEN mortality_30day_flag = 0 THEN los_days ELSE NULL END) AS survivor_los_days
    FROM combined_cohort_data
    WHERE cohort_group = 'General_Cohort'
  ),
  dka_risk_percentile AS (
    SELECT
      SAFE_DIVIDE(
        (SELECT COUNTIF(c.risk_score <= d.mean_risk_score) FROM combined_cohort_data c WHERE c.cohort_group = 'DKA_Cohort'),
        d.total_patients
      ) AS percentile_of_mean_risk_profile
    FROM dka_cohort_stats AS d
  )
SELECT
  ROUND(dka.mean_risk_score, 2) AS dka_cohort_mean_risk_score,
  ROUND(dka.mortality_30day_rate * 100, 2) AS dka_cohort_30d_mortality_rate_pct,
  ROUND(dka_p.percentile_of_mean_risk_profile * 100, 2) AS risk_percentile_for_matched_profile,
  ROUND(dka.aki_rate * 100, 2) AS dka_cohort_aki_rate_pct,
  ROUND(gen.aki_rate * 100, 2) AS general_cohort_aki_rate_pct,
  ROUND(dka.ards_rate * 100, 2) AS dka_cohort_ards_rate_pct,
  ROUND(gen.ards_rate * 100, 2) AS general_cohort_ards_rate_pct,
  ROUND(dka.survivor_los_days, 1) AS dka_cohort_survivor_los_days,
  ROUND(gen.survivor_los_days, 1) AS general_cohort_survivor_los_days,
  dka.total_patients AS dka_cohort_patient_count,
  gen.total_patients AS general_cohort_patient_count
FROM
  dka_cohort_stats AS dka
CROSS JOIN
  general_cohort_stats AS gen
CROSS JOIN
  dka_risk_percentile AS dka_p;
