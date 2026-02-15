WITH
  patient_cohort AS (
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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 75 AND 85
      AND ie.intime IS NOT NULL
  ),
  sbp_measurements_first_48h AS (
    SELECT
      pc.stay_id,
      ce.valuenum
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220050, 51)
      AND DATETIME_DIFF(ce.charttime, pc.intime, HOUR) BETWEEN 0 AND 48
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 50 AND 250
  ),
  avg_sbp_per_stay AS (
    SELECT
      stay_id,
      AVG(valuenum) AS avg_sbp
    FROM
      sbp_measurements_first_48h
    GROUP BY
      stay_id
  )
SELECT
  140 AS target_sbp_value,
  COUNT(stay_id) AS total_stays_in_cohort,
  SUM(CASE WHEN avg_sbp <= 140 THEN 1 ELSE 0 END) AS stays_at_or_below_target,
  ROUND(
    100.0 * SUM(CASE WHEN avg_sbp <= 140 THEN 1 ELSE 0 END) / COUNT(stay_id),
    2
  ) AS percentile_rank_of_target,
  ROUND(AVG(avg_sbp), 2) AS cohort_mean_avg_sbp,
  ROUND(STDDEV(avg_sbp), 2) AS cohort_stddev_avg_sbp,
  ROUND(MIN(avg_sbp), 2) AS cohort_min_avg_sbp,
  ROUND(MAX(avg_sbp), 2) AS cohort_max_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(25)], 2) AS p25_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(50)], 2) AS p50_avg_sbp_median,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(75)], 2) AS p75_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(90)], 2) AS p90_avg_sbp
FROM
  avg_sbp_per_stay;
