WITH
  patient_cohort AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diab ON a.hadm_id = d_diab.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 36 AND 46
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
      AND (
        d_diab.icd_code LIKE 'E11%'
        OR (
          d_diab.icd_version = 9
          AND d_diab.icd_code LIKE '250%'
          AND SUBSTR(d_diab.icd_code, 5, 1) NOT IN ('1', '3')
        )
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
  ),

  antidiabetic_prescriptions AS (
    SELECT
      pc.hadm_id,
      pc.admittime,
      pc.dischtime,
      rx.starttime,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Metformin'
        WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%' THEN 'Sulfonylurea'
        WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%' THEN 'DPP-4 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%canagliflozin%' OR LOWER(rx.drug) LIKE '%dapagliflozin%' OR LOWER(rx.drug) LIKE '%empagliflozin%' OR LOWER(rx.drug) LIKE '%ertugliflozin%' THEN 'SGLT2 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%liraglutide%' OR LOWER(rx.drug) LIKE '%semaglutide%' OR LOWER(rx.drug) LIKE '%exenatide%' OR LOWER(rx.drug) LIKE '%dulaglutide%' OR LOWER(rx.drug) LIKE '%lixisenatide%' THEN 'GLP-1 Agonist'
        WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%' THEN 'Thiazolidinedione'
        ELSE NULL
      END AS medication_class
    FROM
      patient_cohort AS pc
      JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON pc.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN pc.admittime AND pc.dischtime
  ),

  first_initiations AS (
    SELECT
      hadm_id,
      admittime,
      dischtime,
      medication_class,
      MIN(starttime) AS first_starttime
    FROM
      antidiabetic_prescriptions
    WHERE
      medication_class IS NOT NULL
    GROUP BY
      hadm_id,
      admittime,
      dischtime,
      medication_class
  ),

  timed_initiations AS (
    SELECT
      hadm_id,
      medication_class,
      CASE
        WHEN DATETIME_DIFF(first_starttime, admittime, HOUR) <= 12 THEN 1
        ELSE 0
      END AS is_early_initiation,
      CASE
        WHEN DATETIME_DIFF(dischtime, first_starttime, HOUR) <= 48 AND DATETIME_DIFF(first_starttime, admittime, HOUR) > 12 THEN 1
        ELSE 0
      END AS is_late_initiation
    FROM
      first_initiations
  ),

  cohort_total AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_admissions
    FROM
      patient_cohort
  ),

  all_med_classes AS (
    SELECT 'Insulin' AS medication_class UNION ALL
    SELECT 'Metformin' UNION ALL
    SELECT 'Sulfonylurea' UNION ALL
    SELECT 'DPP-4 Inhibitor' UNION ALL
    SELECT 'SGLT2 Inhibitor' UNION ALL
    SELECT 'GLP-1 Agonist' UNION ALL
    SELECT 'Thiazolidinedione'
  ),

  initiation_counts AS (
    SELECT
      medication_class,
      SUM(is_early_initiation) AS early_initiations,
      SUM(is_late_initiation) AS late_initiations
    FROM
      timed_initiations
    GROUP BY
      medication_class
  )

SELECT
  amc.medication_class,
  ct.total_admissions AS cohort_size,
  COALESCE(ic.early_initiations, 0) AS early_initiation_count,
  COALESCE(ic.late_initiations, 0) AS late_initiation_count,
  ROUND(COALESCE(ic.early_initiations, 0) * 100.0 / ct.total_admissions, 2) AS early_initiation_rate_pct,
  ROUND(COALESCE(ic.late_initiations, 0) * 100.0 / ct.total_admissions, 2) AS late_initiation_rate_pct,
  (
    ROUND(COALESCE(ic.late_initiations, 0) * 100.0 / ct.total_admissions, 2) -
    ROUND(COALESCE(ic.early_initiations, 0) * 100.0 / ct.total_admissions, 2)
  ) AS net_change_pp
FROM
  all_med_classes AS amc
  CROSS JOIN cohort_total AS ct
  LEFT JOIN initiation_counts AS ic ON amc.medication_class = ic.medication_class
ORDER BY
  (COALESCE(ic.early_initiations, 0) + COALESCE(ic.late_initiations, 0)) DESC;
