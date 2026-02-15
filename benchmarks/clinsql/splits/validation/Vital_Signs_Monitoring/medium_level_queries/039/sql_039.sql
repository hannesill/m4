WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    ie.stay_id,
    ie.intime,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
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
    AND ie.intime IS NOT NULL
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 83 AND 93
),
map_first_48h AS (
  SELECT
    pc.stay_id,
    ce.valuenum AS map_value
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON pc.stay_id = ce.stay_id
  WHERE
    ce.itemid IN (220052, 225312)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 20 AND 200
    AND ce.charttime BETWEEN pc.intime AND DATETIME_ADD(pc.intime, INTERVAL 48 HOUR)
),
avg_map_per_stay AS (
  SELECT
    stay_id,
    AVG(map_value) AS avg_map
  FROM
    map_first_48h
  GROUP BY
    stay_id
  HAVING
    COUNT(map_value) >= 3
)
SELECT
  ROUND(SAFE_DIVIDE(COUNTIF(avg_map <= 60), COUNT(stay_id)) * 100, 2) AS percentile_rank_of_map_60,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  ROUND(AVG(avg_map), 2) AS cohort_average_map,
  ROUND(STDDEV(avg_map), 2) AS cohort_stddev_map,
  ROUND(MIN(avg_map), 2) AS cohort_min_avg_map,
  ROUND(MAX(avg_map), 2) AS cohort_max_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(10)], 2) AS p10_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(25)], 2) AS p25_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(50)], 2) AS p50_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(75)], 2) AS p75_avg_map,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(90)], 2) AS p90_avg_map
FROM
  avg_map_per_stay;
