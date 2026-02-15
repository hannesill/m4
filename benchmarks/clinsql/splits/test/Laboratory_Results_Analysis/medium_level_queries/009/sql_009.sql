WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND a.admittime IS NOT NULL
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 59 AND 69
  ),
  initial_troponin AS (
    SELECT
      pc.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY pc.hadm_id ORDER BY le.charttime ASC) AS measurement_rank
    FROM
      patient_cohort AS pc
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON pc.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  elevated_initial_troponin_cohort AS (
    SELECT
      hadm_id,
      valuenum AS initial_troponin_t_value
    FROM
      initial_troponin
    WHERE
      measurement_rank = 1
      AND valuenum > 0.014
  )
SELECT
  'Female patients, aged 59-69, with initial hs-TnT > 0.014 ng/mL' AS cohort_description,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(MIN(initial_troponin_t_value), 3) AS min_troponin_t,
  ROUND(APPROX_QUANTILES(initial_troponin_t_value, 100)[OFFSET(25)], 3) AS p25_troponin_t,
  ROUND(APPROX_QUANTILES(initial_troponin_t_value, 100)[OFFSET(50)], 3) AS p50_troponin_t_median,
  ROUND(APPROX_QUANTILES(initial_troponin_t_value, 100)[OFFSET(75)], 3) AS p75_troponin_t,
  ROUND(MAX(initial_troponin_t_value), 3) AS max_troponin_t,
  'ng/mL' AS unit
FROM
  elevated_initial_troponin_cohort;
