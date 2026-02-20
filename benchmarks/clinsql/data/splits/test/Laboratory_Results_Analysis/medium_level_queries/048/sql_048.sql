WITH
  ami_cohort AS (
    SELECT DISTINCT
      a.subject_id,
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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 55 AND 65
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '410%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
      )
  ),
  first_troponin_t AS (
    SELECT
      c.subject_id,
      c.hadm_id,
      le.valuenum AS troponin_t_value,
      ROW_NUMBER() OVER(PARTITION BY c.hadm_id ORDER BY le.charttime ASC) as rn
    FROM
      ami_cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON c.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum > 0
  )
SELECT
  COUNT(DISTINCT subject_id) AS patient_count,
  COUNT(hadm_id) AS admission_count,
  ROUND(AVG(troponin_t_value), 4) AS mean_troponin_t,
  ROUND(APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(50)], 4) AS median_troponin_t,
  ROUND(APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(25)], 4) AS p25_troponin_t,
  ROUND(APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(75)], 4) AS p75_troponin_t,
  ROUND(
    (APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(75)] - APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(25)]),
    4
  ) AS iqr_troponin_t,
  ROUND(MIN(troponin_t_value), 4) AS min_elevated_troponin_t,
  ROUND(MAX(troponin_t_value), 4) AS max_elevated_troponin_t
FROM
  first_troponin_t
WHERE
  rn = 1
  AND troponin_t_value > 0.01;
