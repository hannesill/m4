WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 67 AND 77
  ),
  acs_admissions AS (
    SELECT DISTINCT
      pc.subject_id,
      pc.hadm_id,
      pc.admittime,
      pc.dischtime,
      pc.hospital_expire_flag
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON pc.hadm_id = d.hadm_id
    WHERE
      (d.icd_version = 9 AND (
          d.icd_code LIKE '410%'
          OR d.icd_code LIKE '4111%'
        ))
      OR
      (d.icd_version = 10 AND (
          d.icd_code LIKE 'I200%'
          OR d.icd_code LIKE 'I21%'
          OR d.icd_code LIKE 'I249%'
        ))
  ),
  initial_troponin AS (
    SELECT
      aa.subject_id,
      aa.hadm_id,
      aa.admittime,
      aa.dischtime,
      aa.hospital_expire_flag,
      le.valuenum AS initial_troponin_t,
      ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      acs_admissions AS aa
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON aa.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  final_cohort AS (
    SELECT
      subject_id,
      hadm_id,
      admittime,
      dischtime,
      hospital_expire_flag,
      initial_troponin_t
    FROM
      initial_troponin
    WHERE
      rn = 1
      AND initial_troponin_t > 0.01
  )
SELECT
  'Female Patients, Age 67-77, with ACS and Elevated Initial Troponin T' AS cohort_description,
  COUNT(DISTINCT subject_id) AS patient_count,
  COUNT(DISTINCT hadm_id) AS admission_count,
  ROUND(AVG(initial_troponin_t), 3) AS mean_initial_troponin_t,
  ROUND(APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(50)], 3) AS median_initial_troponin_t,
  ROUND(
    (APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(75)] - APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(25)]),
    3
  ) AS iqr_initial_troponin_t,
  ROUND(MIN(initial_troponin_t), 3) AS min_initial_troponin_t,
  ROUND(MAX(initial_troponin_t), 3) AS max_initial_troponin_t,
  ROUND(AVG(DATETIME_DIFF(dischtime, admittime, DAY)), 1) AS mean_los_days,
  ROUND(CAST(APPROX_QUANTILES(DATETIME_DIFF(dischtime, admittime, DAY), 100)[OFFSET(50)] AS NUMERIC), 1) AS median_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS INT64)) * 100, 2) AS in_hospital_mortality_rate_pct
FROM
  final_cohort
WHERE
  dischtime IS NOT NULL AND admittime IS NOT NULL;
