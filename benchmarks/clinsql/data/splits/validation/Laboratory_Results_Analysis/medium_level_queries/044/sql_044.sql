WITH
patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'M'
    AND a.admittime IS NOT NULL
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 54 AND 64
),
initial_troponin AS (
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
    AND le.valuenum >= 0 AND le.valuenum < 100
),
elevated_initial_troponin AS (
  SELECT
    hadm_id,
    valuenum
  FROM
    initial_troponin
  WHERE
    rn = 1
    AND valuenum > 0.01
)
SELECT
  'Male Patients Aged 54-64 with Initial Elevated Troponin T' AS cohort_description,
  stats.number_of_admissions,
  stats.mean_troponin_t,
  stats.stddev_troponin_t,
  stats.min_troponin_t,
  stats.troponin_quantiles[OFFSET(25)] AS p25_troponin_t,
  stats.troponin_quantiles[OFFSET(50)] AS median_troponin_t,
  stats.troponin_quantiles[OFFSET(75)] AS p75_troponin_t,
  stats.max_troponin_t
FROM (
  SELECT
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(valuenum), 3) AS mean_troponin_t,
    ROUND(STDDEV(valuenum), 3) AS stddev_troponin_t,
    ROUND(MIN(valuenum), 3) AS min_troponin_t,
    APPROX_QUANTILES(valuenum, 100) AS troponin_quantiles,
    ROUND(MAX(valuenum), 3) AS max_troponin_t
  FROM
    elevated_initial_troponin
) AS stats;
