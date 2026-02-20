WITH
  patient_cohort AS (
    SELECT DISTINCT
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diab ON a.hadm_id = d_diab.hadm_id
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 45 AND 55
      AND (
        d_diab.icd_code LIKE 'E10%' OR
        d_diab.icd_code LIKE 'E11%' OR
        d_diab.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%' OR
        d_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
  ),
  medication_initiations_by_patient AS (
    SELECT
      pc.subject_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
        ELSE 'Oral Agent'
      END AS medication_class,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 12 THEN 1
          ELSE 0
        END
      ) AS initiated_first_12h,
      MAX(
        CASE
          WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 72 THEN 1
          ELSE 0
        END
      ) AS initiated_final_72h
    FROM
      patient_cohort AS pc
    JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON pc.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime >= pc.admittime AND rx.starttime <= pc.dischtime
      AND (
        LOWER(rx.drug) LIKE '%insulin%'
        OR LOWER(rx.drug) LIKE '%metformin%'
        OR LOWER(rx.drug) LIKE '%glipizide%'
        OR LOWER(rx.drug) LIKE '%glyburide%'
        OR LOWER(rx.drug) LIKE '%sitagliptin%'
        OR LOWER(rx.drug) LIKE '%linagliptin%'
      )
    GROUP BY
      pc.subject_id,
      medication_class
  ),
  total_cohort_patients AS (
    SELECT
      COUNT(DISTINCT subject_id) AS total_patients
    FROM
      patient_cohort
  )
SELECT
  classes.medication_class,
  total.total_patients AS total_cohort_patients,
  COALESCE(agg.patients_initiated_first_12h, 0) AS patients_initiated_first_12h,
  COALESCE(agg.patients_initiated_final_72h, 0) AS patients_initiated_final_72h,
  ROUND(
    COALESCE(agg.patients_initiated_first_12h, 0) * 100.0 / NULLIF(total.total_patients, 0),
    2
  ) AS initiation_rate_first_12h_pct,
  ROUND(
    COALESCE(agg.patients_initiated_final_72h, 0) * 100.0 / NULLIF(total.total_patients, 0),
    2
  ) AS initiation_rate_final_72h_pct,
  ROUND(
    (
      COALESCE(agg.patients_initiated_first_12h, 0) * 100.0 / NULLIF(total.total_patients, 0)
    ) - (
      COALESCE(agg.patients_initiated_final_72h, 0) * 100.0 / NULLIF(total.total_patients, 0)
    ),
    2
  ) AS absolute_difference_pp
FROM
  (
    SELECT 'Insulin' AS medication_class
    UNION ALL
    SELECT 'Oral Agent' AS medication_class
  ) AS classes
LEFT JOIN (
  SELECT
    medication_class,
    SUM(initiated_first_12h) AS patients_initiated_first_12h,
    SUM(initiated_final_72h) AS patients_initiated_final_72h
  FROM
    medication_initiations_by_patient
  GROUP BY
    medication_class
) AS agg
  ON classes.medication_class = agg.medication_class
CROSS JOIN
  total_cohort_patients AS total
ORDER BY
  classes.medication_class;
