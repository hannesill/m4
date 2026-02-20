WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
),
diagnosis_cohort AS (
  SELECT DISTINCT
    pc.hadm_id,
    pc.subject_id
  FROM
    patient_cohort AS pc
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON pc.hadm_id = d.hadm_id
  WHERE
    (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code LIKE '7865%'))
    OR
    (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code IN ('R07.89', 'R07.9')))
),
initial_troponin AS (
  SELECT
    dc.hadm_id,
    dc.subject_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY dc.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    diagnosis_cohort AS dc
  JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON dc.hadm_id = le.hadm_id
  WHERE
    le.itemid = 51003
    AND le.valuenum IS NOT NULL
    AND le.valuenum > 0
),
elevated_initial_troponin AS (
  SELECT
    hadm_id,
    subject_id,
    valuenum
  FROM
    initial_troponin
  WHERE
    rn = 1
    AND valuenum > 0.014
)
SELECT
  'Male Patients (50-60) with Chest Pain/AMI and Initial Elevated hs-TnT' AS cohort_description,
  COUNT(DISTINCT subject_id) AS patient_count,
  COUNT(hadm_id) AS admission_count,
  ROUND(AVG(valuenum), 3) AS mean_troponin_t,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(50)], 3) AS median_troponin_t,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3) AS p25_troponin_t,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)], 3) AS p75_troponin_t,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)] - APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3) AS iqr_troponin_t
FROM
  elevated_initial_troponin;
