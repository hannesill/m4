WITH
  cohort_stays AS (
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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 80 AND 90
      AND ie.outtime IS NOT NULL
  ),
  stay_avg_hr AS (
    SELECT
      cs.stay_id,
      AVG(ce.valuenum) AS avg_hr
    FROM
      cohort_stays AS cs
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON cs.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220045, 211)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 30 AND 250
    GROUP BY
      cs.stay_id
  )
SELECT
  'Female patients aged 80-90' AS cohort_description,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  ROUND(AVG(avg_hr), 2) AS cohort_mean_of_avg_hr,
  ROUND(STDDEV(avg_hr), 2) AS cohort_stddev_of_avg_hr,
  APPROX_QUANTILES(avg_hr, 100)[OFFSET(25)] AS p25_avg_hr,
  APPROX_QUANTILES(avg_hr, 100)[OFFSET(50)] AS p50_avg_hr_median,
  APPROX_QUANTILES(avg_hr, 100)[OFFSET(75)] AS p75_avg_hr,
  APPROX_QUANTILES(avg_hr, 100)[OFFSET(95)] AS p95_avg_hr,
  ROUND(
    100 * SUM(CASE WHEN avg_hr <= 110 THEN 1 ELSE 0 END) / COUNT(stay_id),
    2
  ) AS percentile_rank_of_110_bpm
FROM
  stay_avg_hr;
