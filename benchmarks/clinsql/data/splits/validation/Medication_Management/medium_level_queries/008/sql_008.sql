WITH
  cohort_diagnoses AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
    HAVING
      COUNTIF(
        (icd_version = 10 AND icd_code LIKE 'E11%')
        OR (icd_version = 9 AND (icd_code LIKE '250__0' OR icd_code LIKE '250__2'))
      ) > 0
      AND
      COUNTIF(
        (icd_version = 10 AND icd_code LIKE 'I50%')
        OR (icd_version = 9 AND icd_code LIKE '428%')
      ) > 0
  ),
  patient_cohort AS (
    SELECT
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
      cohort_diagnoses AS cd
      ON a.hadm_id = cd.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 44 AND 54
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
  ),
  medication_flags_by_admission AS (
    SELECT
      rx.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%'
          OR LOWER(rx.drug) LIKE '%glipizide%'
          OR LOWER(rx.drug) LIKE '%glyburide%'
          OR LOWER(rx.drug) LIKE '%sitagliptin%'
          OR LOWER(rx.drug) LIKE '%linagliptin%'
        THEN 'Oral Agent'
      END AS medication_class,
      COUNTIF(DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 24) > 0 AS on_early,
      COUNTIF(DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48) > 0 AS on_late
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
    INNER JOIN
      patient_cohort AS cohort
      ON rx.hadm_id = cohort.hadm_id
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
    GROUP BY
      rx.hadm_id,
      medication_class
  ),
  all_combinations AS (
    SELECT
      hadm_id,
      medication_class
    FROM
      (SELECT DISTINCT hadm_id FROM patient_cohort)
    CROSS JOIN
      (SELECT 'Insulin' AS medication_class UNION ALL SELECT 'Oral Agent' AS medication_class)
  )
SELECT
  ac.medication_class,
  (SELECT COUNT(DISTINCT hadm_id) FROM patient_cohort) AS total_cohort_admissions,
  ROUND(COUNTIF(COALESCE(mf.on_early, false)) * 100.0 / COUNT(ac.hadm_id), 1) AS prevalence_first_24h_pct,
  ROUND(COUNTIF(COALESCE(mf.on_late, false)) * 100.0 / COUNT(ac.hadm_id), 1) AS prevalence_last_48h_pct,
  COUNTIF(COALESCE(mf.on_early, false) AND COALESCE(mf.on_late, false)) AS continued_on_med,
  COUNTIF(NOT COALESCE(mf.on_early, false) AND COALESCE(mf.on_late, false)) AS initiated_before_discharge,
  COUNTIF(COALESCE(mf.on_early, false) AND NOT COALESCE(mf.on_late, false)) AS discontinued_after_admission,
  COUNTIF(NOT COALESCE(mf.on_early, false) AND NOT COALESCE(mf.on_late, false)) AS not_on_med_in_windows
FROM
  all_combinations AS ac
LEFT JOIN
  medication_flags_by_admission AS mf
  ON ac.hadm_id = mf.hadm_id AND ac.medication_class = mf.medication_class
GROUP BY
  ac.medication_class
ORDER BY
  ac.medication_class;
