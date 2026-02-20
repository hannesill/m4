WITH patient_cohort AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id
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
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 47 AND 57
    AND (
      (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '410' AND '414')
      OR
      (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'I20' AND 'I25')
    )
),
first_troponin AS (
  SELECT
    pc.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY pc.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON pc.hadm_id = le.hadm_id
  WHERE
    le.itemid = 51003
    AND le.valuenum IS NOT NULL
),
elevated_first_troponin AS (
  SELECT
    hadm_id,
    valuenum
  FROM
    first_troponin
  WHERE
    rn = 1
    AND valuenum > 0.014
)
SELECT
  'Male patients, aged 47-57, with cardiac diagnosis and elevated first Troponin T' AS cohort_description,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(50)], 3) AS median_troponin_t_ng_ml,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3) AS p25_troponin_t_ng_ml,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)], 3) AS p75_troponin_t_ng_ml,
  ROUND((APPROX_QUANTILES(valuenum, 100)[OFFSET(75)] - APPROX_QUANTILES(valuenum, 100)[OFFSET(25)]), 3) AS iqr_troponin_t,
  ROUND(MIN(valuenum), 3) AS min_elevated_value,
  ROUND(MAX(valuenum), 3) AS max_elevated_value
FROM
  elevated_first_troponin;
