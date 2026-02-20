WITH
cohort_patients AS (
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
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 68 AND 78
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
    AND (
      (d_diabetes.icd_version = 10 AND d_diabetes.icd_code LIKE 'E11%')
      OR (d_diabetes.icd_version = 9 AND d_diabetes.icd_code LIKE '250.%' AND SUBSTR(d_diabetes.icd_code, 5, 1) IN ('0', '2'))
    )
    AND (
      (d_hf.icd_version = 10 AND d_hf.icd_code LIKE 'I50%')
      OR (d_hf.icd_version = 9 AND d_hf.icd_code LIKE '428%')
    )
),
cohort_total AS (
  SELECT
    COUNT(DISTINCT hadm_id) AS total_patients
  FROM
    cohort_patients
),
medication_events AS (
  SELECT
    c.hadm_id,
    CASE
      WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Metformin'
      WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%' THEN 'Sulfonylureas'
      WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%' THEN 'DPP-4 Inhibitors'
      WHEN LOWER(rx.drug) LIKE '%gliflozin%' THEN 'SGLT2 Inhibitors'
      WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%' THEN 'Thiazolidinediones'
      ELSE NULL
    END AS drug_class,
    CASE
      WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) < 48 THEN 'Early_Admission'
      WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 12 THEN 'Discharge_Period'
      ELSE NULL
    END AS time_window
  FROM
    cohort_patients AS c
    JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON c.hadm_id = rx.hadm_id
  WHERE
    rx.starttime IS NOT NULL
    AND rx.starttime BETWEEN c.admittime AND c.dischtime
),
patient_exposure AS (
  SELECT
    hadm_id,
    drug_class,
    MAX(IF(time_window = 'Early_Admission', 1, 0)) AS given_early,
    MAX(IF(time_window = 'Discharge_Period', 1, 0)) AS given_at_discharge
  FROM
    medication_events
  WHERE
    drug_class IS NOT NULL AND time_window IS NOT NULL
  GROUP BY
    hadm_id,
    drug_class
),
class_counts AS (
  SELECT
    drug_class,
    SUM(given_early) AS patients_early,
    SUM(given_at_discharge) AS patients_discharge
  FROM
    patient_exposure
  GROUP BY
    drug_class
)
SELECT
  cc.drug_class,
  ct.total_patients AS total_cohort_admissions,
  cc.patients_early,
  cc.patients_discharge,
  ROUND((cc.patients_early * 100.0) / ct.total_patients, 2) AS prevalence_early_pct,
  ROUND((cc.patients_discharge * 100.0) / ct.total_patients, 2) AS prevalence_discharge_pct,
  ROUND(
    (cc.patients_discharge * 100.0 / ct.total_patients) - (cc.patients_early * 100.0 / ct.total_patients),
    2
  ) AS net_change_pp
FROM
  class_counts AS cc
  CROSS JOIN cohort_total AS ct
ORDER BY
  cc.patients_early DESC;
