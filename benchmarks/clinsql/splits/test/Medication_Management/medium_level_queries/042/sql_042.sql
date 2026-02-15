WITH
  cohort AS (
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
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diab
      ON a.hadm_id = d_diab.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
      ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 51 AND 61
      AND (
        d_diab.icd_code LIKE 'E10%' OR d_diab.icd_code LIKE 'E11%' OR d_diab.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%' OR d_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
  ),
  medication_periods AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%'
        THEN 'Insulin'
        WHEN
          LOWER(rx.drug) LIKE '%metformin%'
          OR LOWER(rx.drug) LIKE '%glipizide%'
          OR LOWER(rx.drug) LIKE '%glyburide%'
          OR LOWER(rx.drug) LIKE '%sitagliptin%'
          OR LOWER(rx.drug) LIKE '%linagliptin%'
        THEN 'Oral Agents'
        ELSE NULL
      END AS medication_class,
      (
        DATETIME_DIFF(rx.starttime, c.admittime, HOUR) >= 0
        AND DATETIME_DIFF(rx.starttime, c.admittime, HOUR) <= 48
      ) AS is_early,
      (
        DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) >= 0
        AND DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 24
      ) AS is_late
    FROM
      cohort AS c
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
  patient_med_summary AS (
    SELECT
      hadm_id,
      medication_class,
      LOGICAL_OR(is_early) AS received_early,
      LOGICAL_OR(is_late) AS received_late
    FROM
      medication_periods
    WHERE
      medication_class IS NOT NULL
      AND (is_early OR is_late)
    GROUP BY
      hadm_id,
      medication_class
  ),
  cohort_stats AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_patients
    FROM
      cohort
  )
SELECT
  pms.medication_class,
  cs.total_patients AS total_cohort_patients,
  COUNTIF(pms.received_early) AS patients_on_med_early,
  ROUND(
    100.0 * COUNTIF(pms.received_early) / cs.total_patients,
    2
  ) AS prevalence_early_pct,
  COUNTIF(pms.received_late) AS patients_on_med_late,
  ROUND(
    100.0 * COUNTIF(pms.received_late) / cs.total_patients,
    2
  ) AS prevalence_late_pct,
  COUNTIF(pms.received_early AND pms.received_late) AS transition_continued,
  COUNTIF(NOT pms.received_early AND pms.received_late) AS transition_initiated,
  COUNTIF(pms.received_early AND NOT pms.received_late) AS transition_discontinued
FROM
  patient_med_summary AS pms
CROSS JOIN
  cohort_stats AS cs
GROUP BY
  pms.medication_class,
  cs.total_patients
ORDER BY
  pms.medication_class;
