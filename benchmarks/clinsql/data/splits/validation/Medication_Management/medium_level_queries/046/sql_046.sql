WITH
  patient_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes ON a.hadm_id = d_diabetes.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 63 AND 73
      AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
      AND (
        d_diabetes.icd_code LIKE 'E11%'
        OR (d_diabetes.icd_version = 9 AND (d_diabetes.icd_code LIKE '250.%0' OR d_diabetes.icd_code LIKE '250.%2'))
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
  ),
  medication_events AS (
    SELECT
      cohort.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%'
          OR LOWER(rx.drug) LIKE '%glipizide%'
          OR LOWER(rx.drug) LIKE '%glyburide%'
          OR LOWER(rx.drug) LIKE '%sitagliptin%'
          OR LOWER(rx.drug) LIKE '%linagliptin%'
        THEN 'Oral Agent'
        ELSE NULL
      END AS medication_class,
      CASE
        WHEN rx.starttime BETWEEN cohort.admittime AND DATETIME_ADD(cohort.admittime, INTERVAL 24 HOUR) THEN 1
        ELSE 0
      END AS is_first_24hr,
      CASE
        WHEN rx.starttime BETWEEN DATETIME_SUB(cohort.dischtime, INTERVAL 24 HOUR) AND cohort.dischtime THEN 1
        ELSE 0
      END AS is_last_24hr
    FROM
      patient_cohort AS cohort
      JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND (
        LOWER(rx.drug) LIKE '%insulin%'
        OR LOWER(rx.drug) LIKE '%metformin%'
        OR LOWER(rx.drug) LIKE '%glipizide%'
        OR LOWER(rx.drug) LIKE '%glyburide%'
        OR LOWER(rx.drug) LIKE '%sitagliptin%'
        OR LOWER(rx.drug) LIKE '%linagliptin%'
      )
  ),
  patient_period_summary AS (
    SELECT
      hadm_id,
      medication_class,
      MAX(is_first_24hr) AS received_in_first_24hr,
      MAX(is_last_24hr) AS received_in_last_24hr
    FROM
      medication_events
    WHERE
      medication_class IS NOT NULL
    GROUP BY
      hadm_id,
      medication_class
  ),
  class_level_counts AS (
    SELECT
      medication_class,
      SUM(received_in_first_24hr) AS patients_in_first_24hr,
      SUM(received_in_last_24hr) AS patients_in_last_24hr
    FROM
      patient_period_summary
    GROUP BY
      medication_class
  ),
  total_cohort AS (
    SELECT COUNT(DISTINCT hadm_id) AS total_admissions FROM patient_cohort
  )
SELECT
  counts.medication_class,
  total.total_admissions AS total_cohort_admissions,
  counts.patients_in_first_24hr,
  counts.patients_in_last_24hr,
  ROUND(counts.patients_in_first_24hr * 100.0 / total.total_admissions, 2) AS prevalence_first_24hr_pct,
  ROUND(counts.patients_in_last_24hr * 100.0 / total.total_admissions, 2) AS prevalence_last_24hr_pct,
  ROUND(
    (counts.patients_in_last_24hr * 100.0 / total.total_admissions) - (counts.patients_in_first_24hr * 100.0 / total.total_admissions),
    2
  ) AS net_change_pp
FROM
  class_level_counts AS counts
  CROSS JOIN total_cohort AS total
ORDER BY
  counts.medication_class;
