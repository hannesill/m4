WITH
  icu_admissions AS (
    SELECT
      adm.hadm_id,
      adm.subject_id,
      adm.admittime,
      adm.dischtime,
      adm.deathtime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
    WHERE
      pat.gender = 'M'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 88 AND 98
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
        WHERE icu.hadm_id = adm.hadm_id
      )
  ),
  cohort_diagnoses AS (
    SELECT
      hadm_id,
      subject_id,
      icd_code,
      icd_version
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      hadm_id IN (SELECT hadm_id FROM icu_admissions)
  ),
  pneumonia_cohort_hadm_ids AS (
    SELECT DISTINCT
      hadm_id
    FROM
      cohort_diagnoses
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '480' AND '486')
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
  ),
  final_cohort_data AS (
    SELECT
      dx.hadm_id,
      dx.subject_id,
      SUM(
        CASE
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('R68.81', 'R57.0') THEN 25
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('995.92', '785.52') THEN 25
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('R65.21', 'A41.9') THEN 25
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('995.92', '038.9') THEN 25
          WHEN dx.icd_version = 10 AND (dx.icd_code LIKE 'I21%' OR dx.icd_code = 'I46.9') THEN 20
          WHEN dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code = '427.5') THEN 20
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('J96.00', 'J80') THEN 20
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('518.81', '518.82') THEN 20
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('Z51.11', 'R06.03') THEN 10
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('V58.11', '786.03') THEN 10
          ELSE 1
        END
      ) AS composite_risk_score,
      COUNTIF(
          (dx.icd_version = 9 AND dx.icd_code LIKE '584%')
       OR (dx.icd_version = 10 AND dx.icd_code LIKE 'N17%')
      ) > 0 AS has_aki,
      COUNTIF(
          (dx.icd_version = 9 AND dx.icd_code IN ('518.82', '518.5'))
       OR (dx.icd_version = 10 AND dx.icd_code = 'J80')
      ) > 0 AS has_ards
    FROM
      cohort_diagnoses AS dx
      INNER JOIN pneumonia_cohort_hadm_ids AS pci ON dx.hadm_id = pci.hadm_id
    GROUP BY
      dx.hadm_id,
      dx.subject_id
  ),
  final_cohort_stats AS (
    SELECT
      d.hadm_id,
      d.subject_id,
      d.composite_risk_score,
      d.has_aki,
      d.has_ards,
      a.hospital_expire_flag,
      IF(a.hospital_expire_flag = 1, DATETIME_DIFF(a.deathtime, a.admittime, DAY), NULL) AS survival_days_if_deceased,
      ROUND(PERCENT_RANK() OVER (ORDER BY d.composite_risk_score) * 100, 2) AS risk_score_percentile_rank
    FROM
      final_cohort_data AS d
      INNER JOIN icu_admissions AS a ON d.hadm_id = a.hadm_id
  )
SELECT
  'Male Patients, Age 88-98 at Admission, with Pneumonia & ICU Stay' AS cohort_description,
  COUNT(hadm_id) AS total_patients_in_cohort,
  MIN(composite_risk_score) AS min_risk_score,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(25)] AS risk_score_25th_percentile,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(50)] AS risk_score_median,
  APPROX_QUANTILES(composite_risk_score, 100)[OFFSET(75)] AS risk_score_75th_percentile,
  MAX(composite_risk_score) AS max_risk_score,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS in_hospital_mortality_rate_pct,
  ROUND(AVG(IF(has_aki, 1, 0)) * 100, 2) AS aki_rate_pct,
  ROUND(AVG(IF(has_ards, 1, 0)) * 100, 2) AS ards_rate_pct,
  APPROX_QUANTILES(survival_days_if_deceased, 100)[OFFSET(50)] AS median_survival_days_for_deceased
FROM
  final_cohort_stats;
