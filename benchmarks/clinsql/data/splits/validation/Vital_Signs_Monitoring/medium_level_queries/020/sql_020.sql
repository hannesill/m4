WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 58 AND 68
  ),
  icu_stays_cohort AS (
    SELECT
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
    INNER JOIN
      patient_cohort AS pc
      ON ie.hadm_id = pc.hadm_id
    WHERE
      ie.intime IS NOT NULL
  ),
  map_measurements_first_48h AS (
    SELECT
      isc.stay_id,
      ce.valuenum
    FROM
      icu_stays_cohort AS isc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON isc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220052, 52)
      AND ce.charttime <= DATETIME_ADD(isc.intime, INTERVAL 48 HOUR)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 30 AND 200
  ),
  avg_map_per_stay AS (
    SELECT
      stay_id,
      AVG(valuenum) AS avg_map
    FROM
      map_measurements_first_48h
    GROUP BY
      stay_id
  )
SELECT
  85 AS target_map_value_mmhg,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(avg_map <= 85),
      COUNT(stay_id)
    ) * 100,
    2
  ) AS percentile_rank_of_target_map,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  ROUND(AVG(avg_map), 2) AS cohort_mean_of_avg_map,
  ROUND(STDDEV(avg_map), 2) AS cohort_stddev_of_avg_map,
  ROUND(MIN(avg_map), 2) AS cohort_min_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(25)], 2) AS cohort_p25_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(50)], 2) AS cohort_p50_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(75)], 2) AS cohort_p75_avg_map,
  ROUND(MAX(avg_map), 2) AS cohort_max_avg_map
FROM
  avg_map_per_stay;
