WITH
  male_patients_in_age_range AS (
    SELECT
      p.subject_id,
      ie.stay_id,
      ie.intime
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
      AND (p.anchor_age + EXTRACT(YEAR FROM ie.intime) - p.anchor_year) BETWEEN 81 AND 91
      AND ie.intime IS NOT NULL
  ),

  sbp_measurements_first_48h AS (
    SELECT
      pat.stay_id,
      ce.valuenum AS sbp_value
    FROM
      male_patients_in_age_range AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pat.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220050, 51)
      AND ce.valuenum IS NOT NULL
      AND DATETIME_DIFF(ce.charttime, pat.intime, HOUR) BETWEEN 0 AND 48
      AND ce.valuenum > 40 AND ce.valuenum < 300
  ),

  avg_sbp_per_stay AS (
    SELECT
      stay_id,
      AVG(sbp_value) AS avg_sbp
    FROM
      sbp_measurements_first_48h
    GROUP BY
      stay_id
  )

SELECT
  'Male ICU patients aged 81-91' AS cohort_description,
  'First 48 hours of ICU stay' AS measurement_period,
  'Average Systolic Blood Pressure (mmHg)' AS metric,
  ROUND(
    100 * (
      COUNTIF(avg_sbp <= 150) / COUNT(stay_id)
    ),
    2
  ) AS percentile_rank_of_150_mmhg,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  ROUND(AVG(avg_sbp), 2) AS mean_avg_sbp,
  ROUND(STDDEV(avg_sbp), 2) AS stddev_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(25)], 2) AS p25_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(50)], 2) AS p50_avg_sbp_median,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(75)], 2) AS p75_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(90)], 2) AS p90_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(95)], 2) AS p95_avg_sbp,
  ROUND(MIN(avg_sbp), 2) AS min_avg_sbp,
  ROUND(MAX(avg_sbp), 2) AS max_avg_sbp
FROM
  avg_sbp_per_stay;
