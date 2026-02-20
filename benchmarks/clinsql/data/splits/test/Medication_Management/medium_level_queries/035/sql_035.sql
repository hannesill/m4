WITH
patient_cohort AS (
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
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 57 AND 67
    AND (
      d_diabetes.icd_code LIKE 'E10%'
      OR d_diabetes.icd_code LIKE 'E11%'
      OR d_diabetes.icd_code LIKE '250%'
    )
    AND (
      d_hf.icd_code LIKE 'I50%'
      OR d_hf.icd_code LIKE '428%'
    )
    AND a.dischtime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
),
glp1_prescriptions AS (
  SELECT
    cohort.hadm_id,
    CASE
      WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 48 THEN 'Early_Admission_48h'
      WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12 THEN 'Final_Discharge_12h'
      ELSE 'Mid_Stay'
    END AS time_window
  FROM
    patient_cohort AS cohort
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
    ON cohort.hadm_id = rx.hadm_id
  WHERE
    (
      LOWER(rx.drug) LIKE '%semaglutide%'
      OR LOWER(rx.drug) LIKE '%liraglutide%'
      OR LOWER(rx.drug) LIKE '%dulaglutide%'
      OR LOWER(rx.drug) LIKE '%exenatide%'
    )
    AND rx.starttime IS NOT NULL
    AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
),
summary_metrics AS (
  SELECT
    (SELECT COUNT(DISTINCT hadm_id) FROM patient_cohort) AS total_cohort_admissions,
    COUNT(DISTINCT CASE WHEN time_window = 'Early_Admission_48h' THEN hadm_id END) AS early_window_admissions,
    COUNT(DISTINCT CASE WHEN time_window = 'Final_Discharge_12h' THEN hadm_id END) AS final_window_admissions
  FROM
    glp1_prescriptions
)
SELECT
  'GLP-1 Receptor Agonists' AS medication_class,
  sm.total_cohort_admissions,
  sm.early_window_admissions,
  sm.final_window_admissions,
  ROUND(SAFE_DIVIDE(sm.early_window_admissions, sm.total_cohort_admissions) * 100, 3) AS early_prevalence_pct,
  ROUND(SAFE_DIVIDE(sm.final_window_admissions, sm.total_cohort_admissions) * 100, 3) AS final_prevalence_pct,
  ROUND(
    (SAFE_DIVIDE(sm.final_window_admissions, sm.total_cohort_admissions) * 100)
    - (SAFE_DIVIDE(sm.early_window_admissions, sm.total_cohort_admissions) * 100),
    3
  ) AS absolute_change_pct_points,
  ROUND(
    SAFE_DIVIDE(
      (SAFE_DIVIDE(sm.final_window_admissions, sm.total_cohort_admissions) - SAFE_DIVIDE(sm.early_window_admissions, sm.total_cohort_admissions)),
      SAFE_DIVIDE(sm.early_window_admissions, sm.total_cohort_admissions)
    ) * 100,
    2
  ) AS relative_change_pct
FROM
  summary_metrics AS sm;
