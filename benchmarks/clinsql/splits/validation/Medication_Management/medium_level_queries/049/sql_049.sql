WITH patient_cohort AS (
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
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 66 AND 76
    AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
    AND (
      d_diabetes.icd_code LIKE '250%'
      OR d_diabetes.icd_code LIKE 'E08%'
      OR d_diabetes.icd_code LIKE 'E09%'
      OR d_diabetes.icd_code LIKE 'E10%'
      OR d_diabetes.icd_code LIKE 'E11%'
      OR d_diabetes.icd_code LIKE 'E13%'
    )
    AND (
      d_hf.icd_code LIKE '428%'
      OR d_hf.icd_code LIKE 'I50%'
    )
),
medication_events AS (
  SELECT DISTINCT
    cohort.hadm_id,
    CASE
      WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) < 72 THEN 'First_72_Hours'
      WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) <= 24 THEN 'Final_24_Hours'
      ELSE NULL
    END AS time_window,
    CASE
      WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
      WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Metformin'
      WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%' THEN 'Sulfonylurea'
      WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%' THEN 'DPP-4 Inhibitor'
      WHEN LOWER(rx.drug) LIKE '%gliflozin%' THEN 'SGLT2 Inhibitor'
      WHEN LOWER(rx.drug) LIKE '%glutide%' OR LOWER(rx.drug) LIKE '%enatide%' THEN 'GLP-1 Agonist'
      WHEN LOWER(rx.drug) LIKE '%glitazone%' THEN 'Thiazolidinedione'
      ELSE NULL
    END AS medication_class
  FROM
    patient_cohort AS cohort
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
    ON cohort.hadm_id = rx.hadm_id
  WHERE
    rx.starttime IS NOT NULL
    AND rx.starttime >= cohort.admittime AND rx.starttime <= cohort.dischtime
),
cohort_total AS (
  SELECT COUNT(DISTINCT hadm_id) AS total_admissions
  FROM patient_cohort
),
all_med_classes AS (
  SELECT 'Insulin' AS medication_class UNION ALL
  SELECT 'Metformin' UNION ALL
  SELECT 'Sulfonylurea' UNION ALL
  SELECT 'DPP-4 Inhibitor' UNION ALL
  SELECT 'SGLT2 Inhibitor' UNION ALL
  SELECT 'GLP-1 Agonist' UNION ALL
  SELECT 'Thiazolidinedione'
)
SELECT
  amc.medication_class,
  ROUND(
    COUNT(DISTINCT CASE WHEN me.time_window = 'First_72_Hours' AND me.medication_class = amc.medication_class THEN me.hadm_id END) * 100.0 /
    NULLIF(ct.total_admissions, 0),
  2) AS prevalence_first_72h_pct,
  ROUND(
    COUNT(DISTINCT CASE WHEN me.time_window = 'Final_24_Hours' AND me.medication_class = amc.medication_class THEN me.hadm_id END) * 100.0 /
    NULLIF(ct.total_admissions, 0),
  2) AS prevalence_final_24h_pct
FROM
  all_med_classes AS amc
CROSS JOIN
  cohort_total AS ct
LEFT JOIN
  medication_events AS me
  ON amc.medication_class = me.medication_class
GROUP BY
  amc.medication_class,
  ct.total_admissions
ORDER BY
  prevalence_first_72h_pct DESC,
  amc.medication_class;
