WITH
  cohort AS (
    SELECT DISTINCT
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag_dm ON a.hadm_id = diag_dm.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag_hf ON a.hadm_id = diag_hf.hadm_id
    WHERE
      p.gender = 'F'
      AND (
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year
      ) BETWEEN 81 AND 91
      AND (
        diag_dm.icd_code LIKE 'E11%'
        OR (
          diag_dm.icd_version = 9
          AND diag_dm.icd_code LIKE '250.__'
          AND SUBSTR(diag_dm.icd_code, 5, 1) IN ('0', '2')
        )
      )
      AND (
        diag_hf.icd_code LIKE 'I50%'
        OR diag_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
  ),
  medication_events AS (
    SELECT
      c.hadm_id,
      c.admittime,
      c.dischtime,
      rx.starttime,
      CASE
        WHEN LOWER(rx.drug) LIKE '%metformin%'
        THEN 'Metformin'
        WHEN
          LOWER(rx.drug) LIKE '%glipizide%'
          OR LOWER(rx.drug) LIKE '%glyburide%'
          OR LOWER(rx.drug) LIKE '%glimepiride%'
        THEN 'Sulfonylurea'
        WHEN
          LOWER(rx.drug) LIKE '%sitagliptin%'
          OR LOWER(rx.drug) LIKE '%linagliptin%'
          OR LOWER(rx.drug) LIKE '%saxagliptin%'
          OR LOWER(rx.drug) LIKE '%alogliptin%'
        THEN 'DPP-4 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%gliflozin%'
        THEN 'SGLT2 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%glitazone%'
        THEN 'Thiazolidinedione'
        ELSE NULL
      END AS medication_class
    FROM
      cohort AS c
      JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL AND rx.starttime BETWEEN c.admittime AND c.dischtime
      AND LOWER(rx.route) IN ('po', 'po/ng', 'po/gt')
  ),
  all_classes AS (
    SELECT 'Metformin' AS medication_class
    UNION ALL
    SELECT 'Sulfonylurea' AS medication_class
    UNION ALL
    SELECT 'DPP-4 Inhibitor' AS medication_class
    UNION ALL
    SELECT 'SGLT2 Inhibitor' AS medication_class
    UNION ALL
    SELECT 'Thiazolidinedione' AS medication_class
  ),
  timed_medication_counts AS (
    SELECT
      ac.medication_class,
      COUNT(
        DISTINCT CASE
          WHEN DATETIME_DIFF(me.starttime, me.admittime, HOUR) BETWEEN 0 AND 72
          THEN me.hadm_id
          ELSE NULL
        END
      ) AS patients_early_72h,
      COUNT(
        DISTINCT CASE
          WHEN DATETIME_DIFF(me.dischtime, me.starttime, HOUR) BETWEEN 0 AND 48
          THEN me.hadm_id
          ELSE NULL
        END
      ) AS patients_late_48h
    FROM
      all_classes AS ac
      LEFT JOIN medication_events AS me ON ac.medication_class = me.medication_class
    GROUP BY
      ac.medication_class
  ),
  total_cohort_size AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_patients
    FROM
      cohort
  )
SELECT
  tmc.medication_class,
  tcs.total_patients,
  tmc.patients_early_72h,
  tmc.patients_late_48h,
  ROUND((tmc.patients_early_72h * 100.0) / tcs.total_patients, 2) AS prevalence_early_pct,
  ROUND((tmc.patients_late_48h * 100.0) / tcs.total_patients, 2) AS prevalence_late_pct,
  ROUND(
    ((tmc.patients_late_48h * 100.0) / tcs.total_patients) - ((tmc.patients_early_72h * 100.0) / tcs.total_patients),
    2
  ) AS absolute_diff_pp
FROM
  timed_medication_counts AS tmc
  CROSS JOIN total_cohort_size AS tcs
ORDER BY
  tmc.medication_class;
