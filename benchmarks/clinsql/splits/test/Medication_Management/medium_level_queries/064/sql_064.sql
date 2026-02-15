WITH
  cohort AS (
    SELECT
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 71 AND 81
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
    GROUP BY
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime
    HAVING
      COUNT(DISTINCT
        CASE
          WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '250'
          THEN d.icd_code
          WHEN d.icd_version = 10 AND (SUBSTR(d.icd_code, 1, 3) = 'E10' OR SUBSTR(d.icd_code, 1, 3) = 'E11')
          THEN d.icd_code
        END) > 0
      AND COUNT(DISTINCT
        CASE
          WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '428'
          THEN d.icd_code
          WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) = 'I50'
          THEN d.icd_code
        END) > 0
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
        WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%'
        THEN 'Sulfonylureas'
        WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%'
        THEN 'DPP-4 Inhibitors'
        WHEN LOWER(rx.drug) LIKE '%canagliflozin%' OR LOWER(rx.drug) LIKE '%dapagliflozin%' OR LOWER(rx.drug) LIKE '%empagliflozin%'
        THEN 'SGLT2 Inhibitors'
        WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%'
        THEN 'Thiazolidinediones'
        ELSE NULL
      END AS medication_class
    FROM
      cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
  ),
  window_prescriptions AS (
    SELECT
      hadm_id,
      medication_class,
      MAX(
        CASE
          WHEN DATETIME_DIFF(starttime, admittime, HOUR) <= 72
          THEN 1
          ELSE 0
        END
      ) AS prescribed_in_first_72h,
      MAX(
        CASE
          WHEN DATETIME_DIFF(dischtime, starttime, HOUR) <= 48
          THEN 1
          ELSE 0
        END
      ) AS prescribed_in_last_48h
    FROM
      medication_events
    WHERE
      medication_class IS NOT NULL
    GROUP BY
      hadm_id,
      medication_class
  ),
  all_classes AS (
    SELECT 'Metformin' AS medication_class UNION ALL
    SELECT 'Sulfonylureas' UNION ALL
    SELECT 'DPP-4 Inhibitors' UNION ALL
    SELECT 'SGLT2 Inhibitors' UNION ALL
    SELECT 'Thiazolidinediones'
  ),
  class_counts AS (
    SELECT
      ac.medication_class,
      COUNT(DISTINCT
        CASE
          WHEN wp.prescribed_in_first_72h = 1
          THEN wp.hadm_id
        END
      ) AS early_window_count,
      COUNT(DISTINCT
        CASE
          WHEN wp.prescribed_in_last_48h = 1
          THEN wp.hadm_id
        END
      ) AS late_window_count
    FROM
      all_classes AS ac
    LEFT JOIN
      window_prescriptions AS wp
      ON ac.medication_class = wp.medication_class
    GROUP BY
      ac.medication_class
  ),
  cohort_total AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_admissions
    FROM
      cohort
  )
SELECT
  cc.medication_class,
  ROUND(cc.early_window_count * 100.0 / ct.total_admissions, 2) AS initiation_rate_first_72h_pct,
  ROUND(cc.late_window_count * 100.0 / ct.total_admissions, 2) AS initiation_rate_last_48h_pct
FROM
  class_counts AS cc,
  cohort_total AS ct
ORDER BY
  cc.medication_class;
