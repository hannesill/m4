WITH
patient_cohort AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx_diabetes ON a.hadm_id = dx_diabetes.hadm_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx_hf ON a.hadm_id = dx_hf.hadm_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 40 AND 50
    AND (
      dx_diabetes.icd_code LIKE '250%'
      OR dx_diabetes.icd_code LIKE 'E08%' OR dx_diabetes.icd_code LIKE 'E09%' OR dx_diabetes.icd_code LIKE 'E10%' OR dx_diabetes.icd_code LIKE 'E11%' OR dx_diabetes.icd_code LIKE 'E13%'
    )
    AND (
      dx_hf.icd_code LIKE '428%'
      OR dx_hf.icd_code LIKE 'I50%'
    )
    AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) > 48
),
medication_events AS (
  SELECT
    cohort.hadm_id,
    rx.starttime,
    cohort.admittime,
    cohort.dischtime,
    CASE
      WHEN LOWER(rx.drug) LIKE '%insulin%' OR LOWER(rx.drug) LIKE 'metformin%' OR LOWER(rx.drug) LIKE 'glipizide%' OR LOWER(rx.drug) LIKE 'glyburide%' OR LOWER(rx.drug) LIKE 'sitagliptin%' OR LOWER(rx.drug) LIKE 'linagliptin%'
        THEN 'Antidiabetic'
      WHEN LOWER(rx.drug) LIKE 'metoprolol%' OR LOWER(rx.drug) LIKE 'carvedilol%' OR LOWER(rx.drug) LIKE 'bisoprolol%' OR LOWER(rx.drug) LIKE 'atenolol%' OR LOWER(rx.drug) LIKE 'labetalol%'
        THEN 'Beta-Blocker'
      WHEN LOWER(rx.drug) LIKE 'lisinopril%' OR LOWER(rx.drug) LIKE 'losartan%' OR LOWER(rx.drug) LIKE 'valsartan%' OR LOWER(rx.drug) LIKE 'enalapril%' OR LOWER(rx.drug) LIKE 'ramipril%' OR LOWER(rx.drug) LIKE '%sacubitril%'
        THEN 'ACEi/ARB/ARNI'
      WHEN LOWER(rx.drug) LIKE 'furosemide%' OR LOWER(rx.drug) LIKE 'bumetanide%' OR LOWER(rx.drug) LIKE 'torsemide%'
        THEN 'Loop Diuretic'
      ELSE NULL
    END AS med_class
  FROM
    patient_cohort AS cohort
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
  WHERE
    rx.starttime IS NOT NULL
    AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
),
patient_class_exposure AS (
  SELECT
    hadm_id,
    med_class,
    MAX(CASE WHEN DATETIME_DIFF(starttime, admittime, HOUR) <= 24 THEN 1 ELSE 0 END) AS prescribed_early,
    MAX(CASE WHEN DATETIME_DIFF(dischtime, starttime, HOUR) <= 24 THEN 1 ELSE 0 END) AS prescribed_late
  FROM
    medication_events
  WHERE
    med_class IS NOT NULL
  GROUP BY
    hadm_id,
    med_class
),
all_combinations AS (
  SELECT
    hadm_id,
    med_class
  FROM
    (SELECT DISTINCT hadm_id FROM patient_cohort) AS h
    CROSS JOIN (
      SELECT 'Antidiabetic' AS med_class UNION ALL
      SELECT 'Beta-Blocker' AS med_class UNION ALL
      SELECT 'ACEi/ARB/ARNI' AS med_class UNION ALL
      SELECT 'Loop Diuretic' AS med_class
    ) AS m
),
transition_status AS (
  SELECT
    ac.hadm_id,
    ac.med_class,
    CASE
      WHEN COALESCE(pce.prescribed_early, 0) = 1 AND COALESCE(pce.prescribed_late, 0) = 1 THEN 'Continued'
      WHEN COALESCE(pce.prescribed_early, 0) = 0 AND COALESCE(pce.prescribed_late, 0) = 1 THEN 'Initiated Late'
      WHEN COALESCE(pce.prescribed_early, 0) = 1 AND COALESCE(pce.prescribed_late, 0) = 0 THEN 'Discontinued'
      ELSE 'Not Prescribed in Windows'
    END AS transition
  FROM
    all_combinations AS ac
    LEFT JOIN patient_class_exposure AS pce ON ac.hadm_id = pce.hadm_id AND ac.med_class = pce.med_class
),
cohort_size AS (
  SELECT COUNT(DISTINCT hadm_id) AS total_patients FROM patient_cohort
)
SELECT
  ts.med_class,
  cs.total_patients,
  ROUND(
    SUM(CASE WHEN ts.transition IN ('Continued', 'Discontinued') THEN 1 ELSE 0 END) * 100.0 / cs.total_patients, 1
  ) AS pct_on_med_first_24h,
  ROUND(
    SUM(CASE WHEN ts.transition IN ('Continued', 'Initiated Late') THEN 1 ELSE 0 END) * 100.0 / cs.total_patients, 1
  ) AS pct_on_med_last_24h,
  SUM(CASE WHEN ts.transition = 'Continued' THEN 1 ELSE 0 END) AS count_continued,
  SUM(CASE WHEN ts.transition = 'Initiated Late' THEN 1 ELSE 0 END) AS count_initiated_late,
  SUM(CASE WHEN ts.transition = 'Discontinued' THEN 1 ELSE 0 END) AS count_discontinued
FROM
  transition_status AS ts
  CROSS JOIN cohort_size AS cs
GROUP BY
  ts.med_class,
  cs.total_patients
ORDER BY
  ts.med_class;
