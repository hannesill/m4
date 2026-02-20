WITH
  cohort_stays AS (
    SELECT
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 67 AND 77
      AND ie.intime IS NOT NULL
  ),
  first_24h_temps AS (
    SELECT
      cs.stay_id,
      CASE
        WHEN ce.itemid IN (223762, 676) THEN ce.valuenum
        WHEN ce.itemid IN (223761, 678) THEN (ce.valuenum - 32) * 5 / 9
      END AS temperature_celsius
    FROM
      cohort_stays AS cs
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON cs.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (223762, 223761, 676, 678)
      AND ce.charttime BETWEEN cs.intime AND DATETIME_ADD(cs.intime, INTERVAL 24 HOUR)
      AND ce.valuenum IS NOT NULL
  ),
  avg_stay_temps AS (
    SELECT
      stay_id,
      AVG(t.temperature_celsius) AS avg_temp_celsius
    FROM
      first_24h_temps AS t
    WHERE
      t.temperature_celsius BETWEEN 25 AND 45
    GROUP BY
      stay_id
  )
SELECT
  36.0 AS target_temperature_celsius,
  ROUND(
    100 * COUNTIF(ast.avg_temp_celsius <= 36.0) / COUNT(ast.stay_id),
    2
  ) AS percentile_rank_of_target_temp,
  COUNT(ast.stay_id) AS total_icu_stays_in_cohort,
  ROUND(AVG(ast.avg_temp_celsius), 2) AS cohort_mean_avg_temp,
  ROUND(STDDEV(ast.avg_temp_celsius), 2) AS cohort_stddev_avg_temp,
  ROUND(MIN(ast.avg_temp_celsius), 2) AS cohort_min_avg_temp,
  ROUND(MAX(ast.avg_temp_celsius), 2) AS cohort_max_avg_temp,
  ROUND(APPROX_QUANTILES(ast.avg_temp_celsius, 100)[OFFSET(25)], 2) AS p25_avg_temp,
  ROUND(APPROX_QUANTILES(ast.avg_temp_celsius, 100)[OFFSET(50)], 2) AS p50_avg_temp_median,
  ROUND(APPROX_QUANTILES(ast.avg_temp_celsius, 100)[OFFSET(75)], 2) AS p75_avg_temp
FROM
  avg_stay_temps AS ast;
