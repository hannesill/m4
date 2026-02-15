WITH
  cohort_patients AS (
    SELECT
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 73 AND 83
      AND ie.intime IS NOT NULL
  ),
  spo2_measurements_first_24h AS (
    SELECT
      cp.stay_id,
      ce.valuenum
    FROM
      cohort_patients AS cp
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON cp.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220277, 646)
      AND ce.charttime BETWEEN cp.intime AND DATETIME_ADD(cp.intime, INTERVAL 24 HOUR)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 70 AND 100
  ),
  avg_spo2_per_stay AS (
    SELECT
      stay_id,
      AVG(valuenum) AS avg_spo2
    FROM
      spo2_measurements_first_24h
    GROUP BY
      stay_id
  )
SELECT
  92 AS target_spo2_value,
  COUNT(stay_id) AS total_stays_in_cohort,
  SUM(CASE WHEN avg_spo2 <= 92 THEN 1 ELSE 0 END) AS stays_at_or_below_target,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(CASE WHEN avg_spo2 <= 92 THEN 1 ELSE 0 END),
      COUNT(stay_id)
    ),
    2
  ) AS percentile_rank_of_92,
  ROUND(AVG(avg_spo2), 2) AS cohort_mean_avg_spo2,
  ROUND(STDDEV(avg_spo2), 2) AS cohort_stddev_avg_spo2,
  ROUND(MIN(avg_spo2), 2) AS cohort_min_avg_spo2,
  ROUND(MAX(avg_spo2), 2) AS cohort_max_avg_spo2
FROM
  avg_spo2_per_stay;
