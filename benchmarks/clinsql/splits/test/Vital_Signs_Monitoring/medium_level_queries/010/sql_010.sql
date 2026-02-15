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
      AND (
        p.anchor_age + DATETIME_DIFF(ie.intime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)
      ) BETWEEN 77 AND 87
      AND ie.intime IS NOT NULL
      AND ie.outtime IS NOT NULL
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
      ce.itemid IN (
        220050,
        51
      )
      AND DATETIME_DIFF(ce.charttime, pc.intime, HOUR) BETWEEN 0 AND 48
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 40 AND 300
  ),
  avg_sbp_per_stay AS (
    SELECT
      stay_id,
      AVG(valuenum) AS avg_sbp
    FROM
      sbp_measurements_first_48h
    GROUP BY
      stay_id
  ),
  distribution_stats AS (
    SELECT
      APPROX_QUANTILES(avg_sbp, 100) AS sbp_quantiles,
      COUNT(stay_id) AS total_stays_in_cohort,
      SUM(
        CASE
          WHEN avg_sbp <= 160
          THEN 1
          ELSE 0
        END
      ) AS stays_at_or_below_target,
      AVG(avg_sbp) AS cohort_mean_avg_sbp,
      STDDEV(avg_sbp) AS cohort_stddev_avg_sbp
    FROM
      avg_sbp_per_stay
  )
SELECT
  160 AS target_sbp_value,
  ds.total_stays_in_cohort,
  ds.stays_at_or_below_target,
  ROUND(
    100 * ds.stays_at_or_below_target / ds.total_stays_in_cohort, 2
  ) AS percentile_rank_of_160,
  ROUND(ds.cohort_mean_avg_sbp, 2) AS cohort_mean_avg_sbp,
  ROUND(ds.cohort_stddev_avg_sbp, 2) AS cohort_stddev_avg_sbp,
  ROUND(ds.sbp_quantiles[OFFSET(25)], 2) AS p25_sbp,
  ROUND(ds.sbp_quantiles[OFFSET(50)], 2) AS p50_sbp_median,
  ROUND(ds.sbp_quantiles[OFFSET(75)], 2) AS p75_sbp,
  ROUND(ds.sbp_quantiles[OFFSET(90)], 2) AS p90_sbp,
  ROUND(ds.sbp_quantiles[OFFSET(95)], 2) AS p95_sbp
FROM
  distribution_stats AS ds;
