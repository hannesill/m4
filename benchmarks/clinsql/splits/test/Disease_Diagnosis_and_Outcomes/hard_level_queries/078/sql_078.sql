WITH
patient_admissions AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.deathtime,
    a.hospital_expire_flag,
    EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
),
hf_admissions AS (
  SELECT DISTINCT
    pa.subject_id,
    pa.hadm_id,
    pa.admittime,
    pa.dischtime,
    pa.deathtime,
    pa.hospital_expire_flag
  FROM
    patient_admissions AS pa
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON pa.hadm_id = dx.hadm_id
  WHERE
    pa.age_at_admission BETWEEN 59 AND 69
    AND (
      (dx.icd_version = 10 AND dx.icd_code LIKE 'I50%')
      OR (dx.icd_version = 9 AND dx.icd_code LIKE '428%')
    )
),
comorbidity_flags AS (
  SELECT
    hf.hadm_id,
    MAX(CASE WHEN (dx.icd_version = 10 AND dx.icd_code LIKE 'N17%') OR (dx.icd_version = 9 AND dx.icd_code LIKE '584%') THEN 1 ELSE 0 END) AS has_aki,
    MAX(CASE WHEN (dx.icd_version = 10 AND dx.icd_code = 'J80') OR (dx.icd_version = 9 AND dx.icd_code = '518.82') THEN 1 ELSE 0 END) AS has_ards,
    MAX(CASE WHEN (dx.icd_version = 10 AND dx.icd_code = 'J96.00') OR (dx.icd_version = 9 AND dx.icd_code = '518.81') THEN 1 ELSE 0 END) AS has_acute_resp_failure_non_ards,
    MAX(CASE WHEN (dx.icd_version = 10 AND dx.icd_code IN ('R65.21', 'A41.9')) OR (dx.icd_version = 9 AND dx.icd_code IN ('995.92', '038.9')) THEN 1 ELSE 0 END) AS has_septic_shock,
    MAX(CASE WHEN (dx.icd_version = 10 AND dx.icd_code IN ('R68.81', 'R57.0')) OR (dx.icd_version = 9 AND dx.icd_code IN ('995.92', '785.52')) THEN 1 ELSE 0 END) AS has_multi_organ_failure,
    MAX(CASE WHEN (dx.icd_version = 10 AND (dx.icd_code LIKE 'I21%' OR dx.icd_code = 'I46.9')) OR (dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code = '427.5')) THEN 1 ELSE 0 END) AS has_acute_mi_comp
  FROM
    hf_admissions AS hf
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON hf.hadm_id = dx.hadm_id
  GROUP BY
    hf.hadm_id
),
patient_level_outcomes AS (
  SELECT
    hf.hadm_id,
    hf.hospital_expire_flag,
    COALESCE(cf.has_aki, 0) AS has_aki,
    COALESCE(cf.has_ards, 0) AS has_ards,
    (
      COALESCE(cf.has_multi_organ_failure, 0) * 30 +
      COALESCE(cf.has_septic_shock, 0) * 30 +
      COALESCE(cf.has_ards, 0) * 25 +
      COALESCE(cf.has_acute_mi_comp, 0) * 20 +
      COALESCE(cf.has_acute_resp_failure_non_ards, 0) * 15 +
      COALESCE(cf.has_aki, 0) * 10
    ) AS composite_risk_score,
    CASE
      WHEN hf.hospital_expire_flag = 1 AND hf.deathtime IS NOT NULL
      THEN DATETIME_DIFF(hf.deathtime, hf.admittime, DAY)
      ELSE NULL
    END AS survival_days_if_deceased
  FROM
    hf_admissions AS hf
  LEFT JOIN
    comorbidity_flags AS cf
    ON hf.hadm_id = cf.hadm_id
)
SELECT
  'Female patients, aged 59-69, with Heart Failure' AS cohort_description,
  COUNT(hadm_id) AS total_admissions_in_cohort,
  ROUND(SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(hadm_id)) * 100, 2) AS in_hospital_mortality_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(has_aki), COUNT(hadm_id)) * 100, 2) AS aki_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(has_ards), COUNT(hadm_id)) * 100, 2) AS ards_rate_pct,
  APPROX_QUANTILES(survival_days_if_deceased, 2)[OFFSET(1)] AS median_survival_days_for_deceased,
  MIN(composite_risk_score) AS risk_score_min,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(25)] AS risk_score_p25,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(50)] AS risk_score_median,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(75)] AS risk_score_p75,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(90)] AS risk_score_p90,
  MAX(composite_risk_score) AS risk_score_max
FROM
  patient_level_outcomes;
