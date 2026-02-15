WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.hospital_expire_flag,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
    DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 48 AND 58
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
    AND EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      WHERE a.hadm_id = d.hadm_id
      AND (
        d.icd_code LIKE '430%' OR
        d.icd_code LIKE '431%' OR
        d.icd_code LIKE '432%' OR
        d.icd_code LIKE '433%' OR
        d.icd_code LIKE '434%' OR
        d.icd_code = '436'   OR
        d.icd_code LIKE 'I60%' OR
        d.icd_code LIKE 'I61%' OR
        d.icd_code LIKE 'I62%' OR
        d.icd_code LIKE 'I63%' OR
        d.icd_code = 'I64'
      )
    )
),

comorbidity_counts AS (
  SELECT
    pc.hadm_id,
    COUNT(DISTINCT d.icd_code) AS diagnosis_count
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON pc.hadm_id = d.hadm_id
  GROUP BY
    pc.hadm_id
),

classified_admissions AS (
  SELECT
    pc.hadm_id,
    pc.hospital_expire_flag,
    CASE
      WHEN icu.stay_id IS NOT NULL THEN 'ICU'
      ELSE 'Non-ICU'
    END AS icu_status,
    CASE
      WHEN pc.length_of_stay <= 5 THEN '≤5 days'
      ELSE '>5 days'
    END AS los_category,
    CASE NTILE(3) OVER (ORDER BY cc.diagnosis_count)
      WHEN 1 THEN 'Low Burden'
      WHEN 2 THEN 'Medium Burden'
      WHEN 3 THEN 'High Burden'
    END AS comorbidity_burden
  FROM
    patient_cohort AS pc
  INNER JOIN
    comorbidity_counts AS cc
    ON pc.hadm_id = cc.hadm_id
  LEFT JOIN
    (SELECT DISTINCT hadm_id, stay_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
    ON pc.hadm_id = icu.hadm_id
)

SELECT
  icu_status,
  los_category,
  comorbidity_burden,
  COUNT(*) AS total_patients,
  SUM(hospital_expire_flag) AS total_deaths,
  ROUND(SAFE_DIVIDE(SUM(hospital_expire_flag) * 100.0, COUNT(*)), 2) AS mortality_rate_percent,
  ROUND(
    GREATEST(0,
      (SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*)) - 1.96 * SQRT(SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*)) * (1 - SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*))) / COUNT(*))) * 100.0
    ), 2
  ) AS ci_95_lower_bound,
  ROUND(
    LEAST(100,
      (SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*)) + 1.96 * SQRT(SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*)) * (1 - SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*))) / COUNT(*))) * 100.0
    ), 2
  ) AS ci_95_upper_bound
FROM
  classified_admissions
GROUP BY
  icu_status,
  los_category,
  comorbidity_burden
ORDER BY
  icu_status DESC,
  los_category,
  CASE comorbidity_burden
    WHEN 'Low Burden' THEN 1
    WHEN 'Medium Burden' THEN 2
    WHEN 'High Burden' THEN 3
  END;
