WITH patient_cohort AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 82 AND 92
    AND a.admittime IS NOT NULL
    AND (
      STARTS_WITH(d.icd_code, '410') OR
      STARTS_WITH(d.icd_code, 'I21') OR
      STARTS_WITH(d.icd_code, 'I22') OR
      STARTS_WITH(d.icd_code, '786.5') OR
      STARTS_WITH(d.icd_code, 'R078') OR
      STARTS_WITH(d.icd_code, 'R079')
    )
),
initial_troponin AS (
  SELECT
    le.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN patient_cohort pc ON le.hadm_id = pc.hadm_id
  WHERE
    le.itemid = 51003
    AND le.valuenum IS NOT NULL
    AND le.valuenum >= 0
),
final_cohort_with_elevated_troponin AS (
  SELECT
    pc.subject_id,
    pc.hadm_id,
    it.valuenum AS initial_troponin_t
  FROM
    patient_cohort AS pc
  JOIN
    initial_troponin AS it
    ON pc.hadm_id = it.hadm_id
  WHERE
    it.rn = 1
    AND it.valuenum > 0.01
)
SELECT
  'Female, 82-92, with Chest Pain/AMI and initial Troponin T > 0.01' AS cohort_description,
  COUNT(DISTINCT subject_id) AS number_of_patients,
  COUNT(DISTINCT hadm_id) AS number_of_admissions,
  MIN(initial_troponin_t) AS min_troponin_t,
  APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(25)] AS p25_troponin_t,
  APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(50)] AS p50_troponin_t_median,
  APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(75)] AS p75_troponin_t,
  MAX(initial_troponin_t) AS max_troponin_t
FROM
  final_cohort_with_elevated_troponin;
