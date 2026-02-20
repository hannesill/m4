WITH
  acs_diagnoses AS (
    SELECT
      hadm_id,
      subject_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND (
          icd_code LIKE '410%'
          OR icd_code = '4111'
        )
      )
      OR
      (
        icd_version = 10
        AND (
          icd_code LIKE 'I21%'
          OR icd_code = 'I200'
        )
      )
    GROUP BY
      hadm_id,
      subject_id
  ),
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
    INNER JOIN
      acs_diagnoses AS dx
      ON a.hadm_id = dx.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 73 AND 83
      AND a.dischtime IS NOT NULL
  ),
  initial_troponin AS (
    SELECT
      hadm_id,
      valuenum AS initial_troponin_t_value,
      ROW_NUMBER() OVER (
        PARTITION BY
          hadm_id
        ORDER BY
          charttime ASC
      ) AS rn
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents`
    WHERE
      hadm_id IN (
        SELECT
          hadm_id
        FROM
          patient_cohort
      )
      AND itemid = 51003
      AND valuenum IS NOT NULL
  ),
  final_cohort AS (
    SELECT
      pc.subject_id,
      pc.hadm_id,
      pc.age_at_admission,
      pc.hospital_expire_flag,
      it.initial_troponin_t_value,
      GREATEST(0, DATETIME_DIFF(pc.dischtime, pc.admittime, DAY)) AS length_of_stay_days
    FROM
      patient_cohort AS pc
    INNER JOIN
      initial_troponin AS it
      ON pc.hadm_id = it.hadm_id
    WHERE
      it.rn = 1
      AND it.initial_troponin_t_value > 0.01
  )
SELECT
  'Male Patients, Age 73-83, with ACS and Elevated Initial Troponin T' AS cohort_description,
  COUNT(DISTINCT subject_id) AS number_of_patients,
  COUNT(DISTINCT hadm_id) AS number_of_admissions,
  ROUND(AVG(age_at_admission), 1) AS avg_age_at_admission,
  ROUND(AVG(length_of_stay_days), 1) AS avg_length_of_stay_days,
  ROUND(STDDEV(length_of_stay_days), 1) AS stddev_length_of_stay_days,
  ROUND(AVG(initial_troponin_t_value), 2) AS avg_initial_troponin_t,
  ROUND(STDDEV(initial_troponin_t_value), 2) AS stddev_initial_troponin_t,
  MIN(initial_troponin_t_value) AS min_initial_troponin_t,
  MAX(initial_troponin_t_value) AS max_initial_troponin_t,
  ROUND(
    SUM(hospital_expire_flag) * 100.0 / COUNT(hadm_id),
    2
  ) AS in_hospital_mortality_rate_percent
FROM
  final_cohort;
