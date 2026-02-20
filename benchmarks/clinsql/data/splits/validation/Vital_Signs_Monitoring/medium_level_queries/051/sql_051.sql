WITH
patient_cohort AS (
  SELECT
    ie.stay_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS ie
    ON a.hadm_id = ie.hadm_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 55 AND 65
),
max_hr_per_stay AS (
  SELECT
    pc.stay_id,
    MAX(ce.valuenum) AS max_heart_rate
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON pc.stay_id = ce.stay_id
  WHERE
    ce.itemid IN (220045, 211)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum > 0 AND ce.valuenum < 300
  GROUP BY
    pc.stay_id
)
SELECT
  COUNT(stay_id) AS number_of_icu_stays,
  ROUND(AVG(max_heart_rate), 1) AS avg_of_max_hr,
  ROUND(APPROX_QUANTILES(max_heart_rate, 4)[OFFSET(1)], 1) AS p25_max_hr_q1,
  ROUND(APPROX_QUANTILES(max_heart_rate, 4)[OFFSET(2)], 1) AS median_max_hr,
  ROUND(APPROX_QUANTILES(max_heart_rate, 4)[OFFSET(3)], 1) AS p75_max_hr_q3,
  ROUND(
    APPROX_QUANTILES(max_heart_rate, 4)[OFFSET(3)] - APPROX_QUANTILES(max_heart_rate, 4)[OFFSET(1)],
    1
  ) AS iqr_of_max_hr
FROM
  max_hr_per_stay;
