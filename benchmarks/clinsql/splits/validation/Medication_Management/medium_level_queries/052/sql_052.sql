WITH
  patient_cohort AS (
    SELECT DISTINCT
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes
      ON a.hadm_id = d_diabetes.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
      ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 45 AND 55
      AND (
        d_diabetes.icd_code LIKE 'E11%'
        OR d_diabetes.icd_code LIKE '250.%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
  ),
  medication_periods AS (
    SELECT
      cohort.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%'
        THEN 'Insulin'
        ELSE 'Oral Agents'
      END AS medication_class,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 48
        THEN 'First_48_Hours'
        WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 24
        THEN 'Final_24_Hours'
        ELSE NULL
      END AS time_window
    FROM
      patient_cohort AS cohort
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON cohort.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
      AND (
        LOWER(rx.drug) LIKE '%insulin%'
        OR LOWER(rx.drug) LIKE '%metformin%'
        OR LOWER(rx.drug) LIKE '%glipizide%'
        OR LOWER(rx.drug) LIKE '%glyburide%'
        OR LOWER(rx.drug) LIKE '%sitagliptin%'
        OR LOWER(rx.drug) LIKE '%linagliptin%'
      )
  ),
  period_counts AS (
    SELECT
      time_window,
      medication_class,
      COUNT(DISTINCT hadm_id) AS patient_count
    FROM
      medication_periods
    WHERE
      time_window IS NOT NULL
    GROUP BY
      time_window,
      medication_class
  ),
  total_patients AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_cohort_patients
    FROM
      patient_cohort
  )
SELECT
  pc.medication_class,
  ROUND(
    (
      MAX(
        CASE
          WHEN pc.time_window = 'First_48_Hours'
          THEN pc.patient_count
          ELSE 0
        END
      ) * 100.0
    ) / tp.total_cohort_patients,
    2
  ) AS prevalence_pct_first_48h,
  ROUND(
    (
      MAX(
        CASE
          WHEN pc.time_window = 'Final_24_Hours'
          THEN pc.patient_count
          ELSE 0
        END
      ) * 100.0
    ) / tp.total_cohort_patients,
    2
  ) AS prevalence_pct_final_24h
FROM
  period_counts AS pc
CROSS JOIN
  total_patients AS tp
GROUP BY
  pc.medication_class,
  tp.total_cohort_patients
ORDER BY
  pc.medication_class;
