WITH
  BaseCohort AS (
    SELECT
      p.subject_id,
      p.gender,
      p.anchor_age,
      p.dod,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.deathtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 68 AND 78
  ),
  ICU_Admissions AS (
    SELECT
      bc.subject_id,
      bc.hadm_id,
      bc.admittime,
      bc.dischtime,
      bc.deathtime,
      bc.dod,
      bc.hospital_expire_flag
    FROM
      BaseCohort AS bc
    WHERE EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      WHERE bc.hadm_id = icu.hadm_id
    )
  ),
  ICH_Cohort AS (
    SELECT DISTINCT
      ia.hadm_id,
      ia.subject_id,
      ia.admittime,
      ia.dischtime,
      ia.deathtime,
      ia.dod,
      ia.hospital_expire_flag
    FROM
      ICU_Admissions AS ia
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON ia.hadm_id = dx.hadm_id
    WHERE
      dx.icd_code LIKE '430%' OR dx.icd_code LIKE '431%' OR dx.icd_code LIKE '432%'
      OR dx.icd_code LIKE 'I60%' OR dx.icd_code LIKE 'I61%' OR dx.icd_code LIKE 'I62%'
  ),
  CohortFeatures AS (
    SELECT
      c.hadm_id,
      c.subject_id,
      c.admittime,
      c.dischtime,
      c.deathtime,
      c.dod,
      c.hospital_expire_flag,
      COUNT(DISTINCT dx.icd_code) AS comorbidity_count,
      MAX(CASE WHEN dx.icd_code IN ('R68.81', 'R57.0', '995.92', '785.52') THEN 1 ELSE 0 END) AS multi_organ_failure_flag,
      MAX(CASE WHEN dx.icd_code IN ('R65.21', 'A41.9', '995.92', '038.9') THEN 1 ELSE 0 END) AS septic_shock_flag,
      MAX(CASE WHEN dx.icd_code LIKE 'I21%' OR dx.icd_code = 'I46.9' OR dx.icd_code LIKE '410%' OR dx.icd_code = '427.5' THEN 1 ELSE 0 END) AS acute_mi_flag,
      MAX(CASE WHEN dx.icd_code IN ('J96.00', 'J80', '518.81', '518.82') THEN 1 ELSE 0 END) AS resp_failure_flag,
      MAX(CASE WHEN dx.icd_code LIKE 'N17%' OR dx.icd_code LIKE '584%' THEN 1 ELSE 0 END) AS aki_flag,
      MAX(CASE WHEN dx.icd_code = 'J80' OR dx.icd_code IN ('518.5', '518.82') THEN 1 ELSE 0 END) AS ards_flag
    FROM
      ICH_Cohort AS c
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON c.hadm_id = dx.hadm_id
    GROUP BY
      c.hadm_id, c.subject_id, c.admittime, c.dischtime, c.deathtime, c.dod, c.hospital_expire_flag
  ),
  PatientLevelData AS (
    SELECT
      *,
      GREATEST(0, DATETIME_DIFF(dischtime, admittime, DAY)) AS los_days,
      (
        (comorbidity_count * 2)
        + (multi_organ_failure_flag * 25)
        + (septic_shock_flag * 25)
        + (acute_mi_flag * 20)
        + (resp_failure_flag * 20)
      ) AS raw_risk_score,
      CASE
        WHEN hospital_expire_flag = 1 THEN 1
        WHEN dod IS NOT NULL AND DATETIME_DIFF(dod, dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS thirty_day_mortality_flag,
      CASE
        WHEN hospital_expire_flag = 1 OR dod IS NOT NULL
        THEN DATETIME_DIFF(COALESCE(deathtime, dod), admittime, DAY)
        ELSE NULL
      END AS survival_days_if_deceased
    FROM
      CohortFeatures
  ),
  RiskNormalized AS (
    SELECT
      pld.*,
      ROUND(
        100 * (pld.raw_risk_score - MIN(pld.raw_risk_score) OVER()) /
        NULLIF(MAX(pld.raw_risk_score) OVER() - MIN(pld.raw_risk_score) OVER(), 0)
      , 0) AS composite_risk_score
    FROM
      PatientLevelData AS pld
  )
SELECT DISTINCT
  COUNT(hadm_id) OVER() AS cohort_patient_count,
  ROUND(AVG(thirty_day_mortality_flag) OVER() * 100, 2) AS mortality_rate_30_day_percent,
  ROUND(AVG(aki_flag) OVER() * 100, 2) AS aki_rate_percent,
  ROUND(AVG(ards_flag) OVER() * 100, 2) AS ards_rate_percent,
  ROUND(PERCENTILE_CONT(composite_risk_score, 0.25) OVER(), 0) AS risk_score_25th_percentile,
  ROUND(PERCENTILE_CONT(composite_risk_score, 0.5) OVER(), 0) AS risk_score_median,
  ROUND(PERCENTILE_CONT(composite_risk_score, 0.75) OVER(), 0) AS risk_score_75th_percentile,
  ROUND(PERCENTILE_CONT(survival_days_if_deceased, 0.5) OVER(), 1) AS median_survival_days_for_deceased
FROM
  RiskNormalized;
