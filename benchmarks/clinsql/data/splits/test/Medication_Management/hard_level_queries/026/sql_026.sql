WITH
pneumonia_admissions AS (
  SELECT DISTINCT
    hadm_id,
    subject_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('480', '481', '482', '483', '484', '485', '486'))
    OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
),
target_cohort_base AS (
  SELECT
    a.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON a.subject_id = p.subject_id
  INNER JOIN
    pneumonia_admissions AS pa
    ON a.hadm_id = pa.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 76 AND 86
),
medication_complexity AS (
  SELECT
    tcb.hadm_id,
    COUNT(DISTINCT pr.drug) AS med_complexity_score
  FROM
    target_cohort_base AS tcb
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
    ON tcb.hadm_id = pr.hadm_id
  WHERE
    pr.starttime >= tcb.admittime AND pr.starttime <= DATETIME_ADD(tcb.admittime, INTERVAL 7 DAY)
  GROUP BY
    tcb.hadm_id
),
patient_admissions_ranked AS (
  SELECT
    subject_id,
    hadm_id,
    admittime,
    dischtime,
    LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions`
  WHERE
    subject_id IN (
      SELECT DISTINCT subject_id FROM target_cohort_base
    )
),
readmissions_flag AS (
  SELECT
    hadm_id,
    CASE
      WHEN DATETIME_DIFF(next_admittime, dischtime, DAY) <= 30 THEN 1
      ELSE 0
    END AS readmitted_30d_flag
  FROM
    patient_admissions_ranked
),
cohort_with_outcomes AS (
  SELECT
    tcb.hadm_id,
    tcb.subject_id,
    DATETIME_DIFF(tcb.dischtime, tcb.admittime, HOUR) / 24.0 AS los_days,
    tcb.hospital_expire_flag,
    COALESCE(mc.med_complexity_score, 0) AS med_complexity_score,
    COALESCE(rf.readmitted_30d_flag, 0) AS readmitted_30d_flag
  FROM
    target_cohort_base AS tcb
  LEFT JOIN
    medication_complexity AS mc
    ON tcb.hadm_id = mc.hadm_id
  LEFT JOIN
    readmissions_flag AS rf
    ON tcb.hadm_id = rf.hadm_id
),
stratified_cohort AS (
  SELECT
    *,
    NTILE(3) OVER (ORDER BY med_complexity_score) AS complexity_tertile
  FROM
    cohort_with_outcomes
)
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS num_admissions,
  MIN(med_complexity_score) AS min_complexity_score,
  ROUND(AVG(med_complexity_score), 2) AS avg_complexity_score,
  MAX(med_complexity_score) AS max_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(readmitted_30d_flag) * 100, 2) AS readmission_30d_rate_percent
FROM
  stratified_cohort
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
