WITH
  target_icu_stays AS (
    SELECT
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 38 AND 48
      AND ie.intime IS NOT NULL
  ),
  avg_sbp_first_48h AS (
    SELECT
      icu.stay_id,
      AVG(ce.valuenum) AS avg_sbp
    FROM
      target_icu_stays AS icu
      INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        ON icu.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (
        220050,
        51
      )
      AND ce.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 48 HOUR)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 40 AND 250
    GROUP BY
      icu.stay_id
  )
SELECT
  130 AS reference_sbp_value,
  COUNT(stay_id) AS total_stays_in_cohort,
  SUM(CASE WHEN avg_sbp <= 130 THEN 1 ELSE 0 END) AS stays_at_or_below_130,
  ROUND(
    100 * SAFE_DIVIDE(
      SUM(CASE WHEN avg_sbp <= 130 THEN 1 ELSE 0 END),
      COUNT(stay_id)
    ),
    2
  ) AS percentile_rank_of_130,
  ROUND(AVG(avg_sbp), 2) AS cohort_mean_avg_sbp,
  ROUND(STDDEV(avg_sbp), 2) AS cohort_stddev_avg_sbp,
  ROUND(MIN(avg_sbp), 2) AS cohort_min_avg_sbp,
  ROUND(MAX(avg_sbp), 2) AS cohort_max_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(25)], 2) AS p25_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(50)], 2) AS p50_median_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(75)], 2) AS p75_avg_sbp
FROM
  avg_sbp_first_48h;
