WITH patient_base AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    p.dod
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 44 AND 54
),
diagnoses_flags AS (
  SELECT
    hadm_id,
    LOGICAL_OR(
      (icd_version = 9 AND (icd_code LIKE '430%' OR icd_code LIKE '431%' OR icd_code LIKE '432%')) OR
      (icd_version = 10 AND (icd_code LIKE 'I60%' OR icd_code LIKE 'I61%' OR icd_code LIKE 'I62%'))
    ) AS has_ich,
    LOGICAL_OR(
      (icd_version = 9 AND (
        icd_code IN ('99592', '78552', '0389', '4275', '51881', '51882', 'V5811', '78603') OR
        icd_code LIKE '410%')
      ) OR
      (icd_version = 10 AND (
        icd_code IN ('R6881', 'R570', 'R6521', 'A419', 'I469', 'J9600', 'J80', 'Z5111', 'R0603') OR
        icd_code LIKE 'I21%')
      )
    ) AS has_major_complication
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  GROUP BY
    hadm_id
),
cohort_outcomes AS (
  SELECT
    pb.subject_id,
    pb.hadm_id,
    COALESCE(df.has_ich, FALSE) AS is_ich_admission,
    COALESCE(df.has_major_complication, FALSE) AS has_major_complication,
    GREATEST(0, IFNULL(DATETIME_DIFF(pb.dischtime, pb.admittime, DAY), 0)) AS los,
    CASE
      WHEN pb.dod IS NOT NULL AND pb.dischtime IS NOT NULL AND pb.dod <= DATETIME_ADD(pb.dischtime, INTERVAL 90 DAY)
      THEN 1
      ELSE 0
    END AS mortality_90day,
    LEAST(100,
      10
      + (CASE WHEN COALESCE(df.has_ich, FALSE) THEN 20 ELSE 0 END)
      + (CASE WHEN COALESCE(df.has_major_complication, FALSE) THEN 30 ELSE 0 END)
      + (5 * GREATEST(0, IFNULL(DATETIME_DIFF(pb.dischtime, pb.admittime, DAY), 0)))
    ) AS risk_score
  FROM
    patient_base AS pb
  LEFT JOIN
    diagnoses_flags AS df
    ON pb.hadm_id = df.hadm_id
)
SELECT
  'ICH Cohort (Female, 44-54)' AS cohort_name,
  COUNT(DISTINCT subject_id) AS num_patients,
  COUNT(hadm_id) AS num_admissions,
  APPROX_QUANTILES(risk_score, 100)[OFFSET(50)] AS median_risk_score,
  (APPROX_QUANTILES(risk_score, 100)[OFFSET(75)] - APPROX_QUANTILES(risk_score, 100)[OFFSET(25)]) AS iqr_risk_score,
  AVG(mortality_90day) AS mortality_90day_rate,
  AVG(CAST(has_major_complication AS INT64)) AS major_complication_rate,
  APPROX_QUANTILES(CASE WHEN mortality_90day = 0 THEN los ELSE NULL END, 100)[OFFSET(50)] AS median_survivor_los_days,
  'A patient with the median risk score for this cohort is at the 50th percentile by definition.' AS matched_profile_risk_percentile
FROM
  cohort_outcomes
WHERE
  is_ich_admission IS TRUE
UNION ALL
SELECT
  'General Cohort (Female, 44-54)' AS cohort_name,
  COUNT(DISTINCT subject_id) AS num_patients,
  COUNT(hadm_id) AS num_admissions,
  APPROX_QUANTILES(risk_score, 100)[OFFSET(50)] AS median_risk_score,
  (APPROX_QUANTILES(risk_score, 100)[OFFSET(75)] - APPROX_QUANTILES(risk_score, 100)[OFFSET(25)]) AS iqr_risk_score,
  AVG(mortality_90day) AS mortality_90day_rate,
  AVG(CAST(has_major_complication AS INT64)) AS major_complication_rate,
  APPROX_QUANTILES(CASE WHEN mortality_90day = 0 THEN los ELSE NULL END, 100)[OFFSET(50)] AS median_survivor_los_days,
  NULL AS matched_profile_risk_percentile
FROM
  cohort_outcomes;
