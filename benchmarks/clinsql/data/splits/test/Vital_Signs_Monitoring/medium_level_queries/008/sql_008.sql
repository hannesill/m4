WITH
  icu_cohort AS (
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
      AND ie.intime IS NOT NULL
  ),
  map_measurements AS (
    SELECT
      cohort.stay_id,
      ce.valuenum AS map_value
    FROM
      icu_cohort AS cohort
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON cohort.stay_id = ce.stay_id
    WHERE
      ce.itemid = 220052
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0 AND ce.valuenum < 200
      AND ce.charttime BETWEEN cohort.intime AND DATETIME_ADD(cohort.intime, INTERVAL 24 HOUR)
  ),
  avg_map_per_stay AS (
    SELECT
      stay_id,
      AVG(map_value) AS avg_map
    FROM
      map_measurements
    GROUP BY
      stay_id
  )
SELECT
  75 AS target_map_value,
  stats.total_stays_in_cohort,
  stats.stays_with_map_lte_75,
  ROUND(
    (stats.stays_with_map_lte_75 * 100.0) / stats.total_stays_in_cohort,
    2
  ) AS percentile_rank_of_75,
  ROUND(stats.cohort_mean_of_avg_map, 2) AS cohort_mean_of_avg_map,
  ROUND(stats.cohort_stddev_of_avg_map, 2) AS cohort_stddev_of_avg_map,
  ROUND(stats.quantiles[OFFSET(0)], 2) AS min_map,
  ROUND(stats.quantiles[OFFSET(25)], 2) AS p25_map,
  ROUND(stats.quantiles[OFFSET(50)], 2) AS p50_map_median,
  ROUND(stats.quantiles[OFFSET(75)], 2) AS p75_map,
  ROUND(stats.quantiles[OFFSET(100)], 2) AS max_map
FROM (
  SELECT
    COUNT(stay_id) AS total_stays_in_cohort,
    COUNTIF(avg_map <= 75) AS stays_with_map_lte_75,
    AVG(avg_map) AS cohort_mean_of_avg_map,
    STDDEV(avg_map) AS cohort_stddev_of_avg_map,
    APPROX_QUANTILES(avg_map, 100) AS quantiles
  FROM avg_map_per_stay
) AS stats;
