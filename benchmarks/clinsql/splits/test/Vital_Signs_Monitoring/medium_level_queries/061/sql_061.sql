WITH
  patient_cohort AS (
    SELECT
      icu.stay_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON p.subject_id = adm.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON adm.hadm_id = icu.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM adm.admittime) - p.anchor_year) BETWEEN 38 AND 48
  ),
  avg_map_per_stay AS (
    SELECT
      pc.stay_id,
      AVG(ce.valuenum) AS avg_map
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (
        220052,
        220181,
        225312,
        456,
        52
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 20 AND 200
    GROUP BY
      pc.stay_id
  )
SELECT
  60 AS target_map_value,
  COUNT(stay_id) AS total_stays_in_cohort,
  SUM(IF(avg_map <= 60, 1, 0)) AS stays_with_avg_map_le_60,
  ROUND(
    (SUM(IF(avg_map <= 60, 1, 0)) / COUNT(stay_id)) * 100,
    2
  ) AS percentile_rank_of_60,
  ROUND(AVG(avg_map), 2) AS cohort_mean_avg_map,
  ROUND(STDDEV(avg_map), 2) AS cohort_stddev_avg_map,
  (APPROX_QUANTILES(avg_map, 100))[OFFSET(25)] AS cohort_p25_avg_map,
  (APPROX_QUANTILES(avg_map, 100))[OFFSET(50)] AS cohort_p50_avg_map,
  (APPROX_QUANTILES(avg_map, 100))[OFFSET(75)] AS cohort_p75_avg_map
FROM
  avg_map_per_stay;
