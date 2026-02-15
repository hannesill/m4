WITH
  base_admissions AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    WHERE
      pat.gender = 'F'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 44 AND 54
  ),
  ich_admissions AS (
    SELECT DISTINCT
      b.subject_id,
      b.hadm_id,
      b.admittime,
      b.dischtime,
      b.hospital_expire_flag,
      b.age_at_admission
    FROM
      base_admissions AS b
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON b.hadm_id = dx.hadm_id
    WHERE
      (dx.icd_version = 9 AND dx.icd_code IN ('430', '431', '432'))
      OR (dx.icd_version = 10 AND (
          dx.icd_code LIKE 'I60%' OR
          dx.icd_code LIKE 'I61%' OR
          dx.icd_code LIKE 'I62%'
        ))
  ),
  diagnosis_features AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT icd_code) AS num_diagnoses,
      MAX(CASE
        WHEN (icd_version = 9 AND (icd_code LIKE '410%' OR icd_code = '427.5'))
          OR (icd_version = 10 AND (icd_code LIKE 'I21%' OR icd_code = 'I46.9'))
        THEN 1 ELSE 0
      END) AS has_cardiac_complication,
      MAX(CASE
        WHEN (icd_version = 9 AND (icd_code = '780.39' OR icd_code LIKE '345%' OR icd_code = '348.5' OR icd_code IN ('331.3', '331.4')))
          OR (icd_version = 10 AND (icd_code = 'R56.9' OR icd_code LIKE 'G40%' OR icd_code = 'G93.6' OR icd_code LIKE 'G91%'))
        THEN 1 ELSE 0
      END) AS has_neuro_complication,
      MAX(CASE
        WHEN (icd_version = 9 AND icd_code IN ('995.92', '785.52', '038.9', '518.81', '518.82', 'V58.11', '786.03'))
          OR (icd_version = 10 AND icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'J96.00', 'J80', 'Z51.11', 'R06.03'))
        THEN 1 ELSE 0
      END) AS has_critical_illness
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      hadm_id IN (SELECT hadm_id FROM ich_admissions)
    GROUP BY
      hadm_id
  ),
  patient_risk_data AS (
    SELECT
      ich.hadm_id,
      ich.hospital_expire_flag,
      feat.has_cardiac_complication,
      feat.has_neuro_complication,
      GREATEST(0, DATETIME_DIFF(ich.dischtime, ich.admittime, DAY)) AS los_days,
      (
        (ich.age_at_admission - 44) * 1 +
        (feat.num_diagnoses) * 2 +
        (feat.has_critical_illness * 25)
      ) AS risk_score
    FROM
      ich_admissions AS ich
    INNER JOIN
      diagnosis_features AS feat
      ON ich.hadm_id = feat.hadm_id
  ),
  stratified_patients AS (
    SELECT
      *,
      NTILE(4) OVER (ORDER BY risk_score) AS risk_quartile
    FROM
      patient_risk_data
  )
SELECT
  risk_quartile,
  COUNT(hadm_id) AS patient_count,
  ROUND(AVG(risk_score), 2) AS avg_risk_score,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS in_hospital_mortality_rate_pct,
  ROUND(AVG(CAST(has_cardiac_complication AS FLOAT64)) * 100, 2) AS cardiac_complication_rate_pct,
  ROUND(AVG(CAST(has_neuro_complication AS FLOAT64)) * 100, 2) AS neuro_complication_rate_pct,
  APPROX_QUANTILES(IF(hospital_expire_flag = 0 AND los_days IS NOT NULL, los_days, NULL), 2)[OFFSET(1)] AS median_survivor_los_days
FROM
  stratified_patients
GROUP BY
  risk_quartile
ORDER BY
  risk_quartile;
