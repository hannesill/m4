WITH
  diabetic_hf_females AS (
    SELECT DISTINCT
      p.subject_id,
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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 38 AND 48
      AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
      AND (
        d_diabetes.icd_code LIKE 'E11%'
        OR d_diabetes.icd_code LIKE '250__0'
        OR d_diabetes.icd_code LIKE '250__2'
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
  ),
  cohort_total AS (
    SELECT
      COUNT(DISTINCT subject_id) AS total_patients
    FROM
      diabetic_hf_females
  ),
  medication_events AS (
    SELECT
      c.subject_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%'
        THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%'
        OR LOWER(rx.drug) LIKE '%glipizide%'
        OR LOWER(rx.drug) LIKE '%glyburide%'
        OR LOWER(rx.drug) LIKE '%sitagliptin%'
        OR LOWER(rx.drug) LIKE '%linagliptin%'
        THEN 'Oral Agents'
      END AS medication_class,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) <= 72
        THEN 1
        ELSE 0
      END AS in_first_72h,
      CASE
        WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 72
        THEN 1
        ELSE 0
      END AS in_final_72h
    FROM
      diabetic_hf_females AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
      AND (
        LOWER(rx.drug) LIKE '%insulin%'
        OR LOWER(rx.drug) LIKE '%metformin%'
        OR LOWER(rx.drug) LIKE '%glipizide%'
        OR LOWER(rx.drug) LIKE '%glyburide%'
        OR LOWER(rx.drug) LIKE '%sitagliptin%'
        OR LOWER(rx.drug) LIKE '%linagliptin%'
      )
  ),
  summary_stats AS (
    SELECT
      medication_class,
      COUNT(DISTINCT CASE WHEN in_first_72h = 1 THEN subject_id END) AS patients_first_72h,
      COUNT(DISTINCT CASE WHEN in_final_72h = 1 THEN subject_id END) AS patients_final_72h
    FROM
      medication_events
    WHERE medication_class IS NOT NULL
    GROUP BY
      medication_class
  )
SELECT
  s.medication_class,
  ROUND(s.patients_first_72h * 100.0 / NULLIF(ct.total_patients, 0), 2) AS initiation_prevalence_first_72h_pct,
  ROUND(s.patients_final_72h * 100.0 / NULLIF(ct.total_patients, 0), 2) AS initiation_prevalence_final_72h_pct
FROM
  summary_stats AS s
CROSS JOIN
  cohort_total AS ct
ORDER BY
  s.medication_class;
