WITH
  cardiac_admissions AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 36 AND 46
      AND (
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '410' AND '414')
        OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'I20' AND 'I25')
      )
  ),
  initial_troponin_t AS (
    SELECT
      ca.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY ca.hadm_id ORDER BY le.charttime ASC) AS measurement_rank
    FROM
      cardiac_admissions AS ca
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON ca.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  )
SELECT
  'Female, 36-46, Cardiac Dx, Initial Elevated hs-TnT' AS cohort_description,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(MIN(valuenum), 4) AS min_troponin_t_ng_ml,
  ROUND(
    APPROX_QUANTILES(valuenum, 100)[OFFSET(25)],
    4
  ) AS p25_troponin_t,
  ROUND(
    APPROX_QUANTILES(valuenum, 100)[OFFSET(50)],
    4
  ) AS p50_median_troponin_t,
  ROUND(
    APPROX_QUANTILES(valuenum, 100)[OFFSET(75)],
    4
  ) AS p75_troponin_t,
  ROUND(MAX(valuenum), 4) AS max_troponin_t_ng_ml,
  ROUND(AVG(valuenum), 4) AS avg_troponin_t_ng_ml
FROM
  initial_troponin_t
WHERE
  measurement_rank = 1
  AND valuenum > 0.014;
