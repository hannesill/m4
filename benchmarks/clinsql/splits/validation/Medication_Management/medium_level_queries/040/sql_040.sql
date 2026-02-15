WITH
  cohort_admissions AS (
    SELECT DISTINCT
      a.subject_id,
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 36 AND 46
      AND (
        d_diabetes.icd_code LIKE 'E10%' OR d_diabetes.icd_code LIKE 'E11%'
        OR d_diabetes.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
  ),
  medication_events AS (
    SELECT
      ca.subject_id,
      ca.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Antidiabetic - Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Antidiabetic - Metformin'
        WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' THEN 'Antidiabetic - Sulfonylurea'
        WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' THEN 'Antidiabetic - DPP4 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%metoprolol%' OR LOWER(rx.drug) LIKE '%carvedilol%' OR LOWER(rx.drug) LIKE '%bisoprolol%' OR LOWER(rx.drug) LIKE '%labetalol%' THEN 'Cardiac - Beta-blocker'
        WHEN LOWER(rx.drug) LIKE '%lisinopril%' OR LOWER(rx.drug) LIKE '%enalapril%' OR LOWER(rx.drug) LIKE '%ramipril%' OR LOWER(rx.drug) LIKE '%losartan%' OR LOWER(rx.drug) LIKE '%valsartan%' OR LOWER(rx.drug) LIKE '%sacubitril%' THEN 'Cardiac - ACEi/ARB/ARNI'
        WHEN LOWER(rx.drug) LIKE '%furosemide%' OR LOWER(rx.drug) LIKE '%bumetanide%' OR LOWER(rx.drug) LIKE '%torsemide%' THEN 'Cardiac - Loop Diuretic'
        ELSE NULL
      END AS medication_class,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, ca.admittime, HOUR) BETWEEN 0 AND 48 THEN 'Early_Admission_48h'
        WHEN DATETIME_DIFF(ca.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12 THEN 'Final_Discharge_12h'
        ELSE NULL
      END AS time_window
    FROM
      cohort_admissions AS ca
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON ca.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN ca.admittime AND ca.dischtime
  ),
  patient_counts_by_window AS (
    SELECT
      medication_class,
      time_window,
      COUNT(DISTINCT subject_id) AS patient_count
    FROM
      medication_events
    WHERE
      medication_class IS NOT NULL AND time_window IS NOT NULL
    GROUP BY
      medication_class,
      time_window
  ),
  final_summary AS (
    SELECT
      medication_class,
      SUM(IF(time_window = 'Early_Admission_48h', patient_count, 0)) AS patients_early,
      SUM(IF(time_window = 'Final_Discharge_12h', patient_count, 0)) AS patients_late,
      (SELECT COUNT(DISTINCT subject_id) FROM cohort_admissions) AS total_cohort_patients
    FROM
      patient_counts_by_window
    GROUP BY
      medication_class
  )
SELECT
  medication_class,
  total_cohort_patients,
  patients_early,
  patients_late,
  ROUND(patients_early * 100.0 / total_cohort_patients, 2) AS prevalence_early_pct,
  ROUND(patients_late * 100.0 / total_cohort_patients, 2) AS prevalence_late_pct,
  ROUND((patients_late * 100.0 / total_cohort_patients) - (patients_early * 100.0 / total_cohort_patients), 2) AS absolute_diff_pct_points
FROM
  final_summary
ORDER BY
  CASE
    WHEN medication_class LIKE 'Cardiac%' THEN 1
    WHEN medication_class LIKE 'Antidiabetic%' THEN 2
    ELSE 3
  END,
  medication_class;
