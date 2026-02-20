WITH
  icu_cohort AS (
    SELECT
      p.subject_id,
      ie.stay_id,
      ie.intime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS admission_age
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
  ),
  filtered_cohort AS (
    SELECT
      stay_id,
      intime
    FROM
      icu_cohort
    WHERE
      admission_age BETWEEN 68 AND 78
  ),
  rr_measurements AS (
    SELECT
      fc.stay_id,
      ce.valuenum AS rr_value
    FROM
      filtered_cohort AS fc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON fc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (
        220210,
        615
      )
      AND ce.charttime BETWEEN fc.intime AND DATETIME_ADD(fc.intime, INTERVAL 48 HOUR)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0 AND ce.valuenum < 60
  ),
  avg_rr_per_stay AS (
    SELECT
      stay_id,
      AVG(rr_value) AS avg_rr
    FROM
      rr_measurements
    GROUP BY
      stay_id
  )
SELECT
  12 AS target_rr_value,
  COUNT(stay_id) AS total_stays_in_cohort,
  SUM(IF(avg_rr <= 12, 1, 0)) AS stays_at_or_below_target,
  ROUND(
    100 * (
      SUM(IF(avg_rr <= 12, 1, 0)) / COUNT(stay_id)
    ),
    2
  ) AS percentile_rank_of_target_rr,
  ROUND(AVG(avg_rr), 2) AS mean_avg_rr,
  ROUND(STDDEV(avg_rr), 2) AS stddev_avg_rr,
  APPROX_QUANTILES(avg_rr, 4) AS quartiles_of_avg_rr
FROM
  avg_rr_per_stay;
