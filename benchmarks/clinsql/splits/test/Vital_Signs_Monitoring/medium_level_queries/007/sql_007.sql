WITH
  target_cohort AS (
    SELECT
      ie.stay_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 80 AND 90
      AND ie.intime IS NOT NULL AND ie.outtime IS NOT NULL
  ),
  avg_spo2_per_stay AS (
    SELECT
      tc.stay_id,
      AVG(ce.valuenum) AS avg_spo2
    FROM
      target_cohort AS tc
      INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON tc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220277, 646)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 50 AND 100
    GROUP BY
      tc.stay_id
    HAVING
      COUNT(ce.valuenum) >= 5
  )
SELECT
  88 AS target_spo2_value,
  ROUND(
    100 * (
      COUNTIF(avg_spo2 <= 88) / COUNT(*)
    ),
    2
  ) AS percentile_rank_of_target,
  COUNT(*) AS total_stays_in_cohort,
  COUNTIF(avg_spo2 <= 88) AS stays_at_or_below_target,
  ROUND(AVG(avg_spo2), 2) AS cohort_mean_avg_spo2,
  ROUND(STDDEV(avg_spo2), 2) AS cohort_stddev_avg_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(5)], 2) AS p5_avg_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(25)], 2) AS p25_avg_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(50)], 2) AS p50_avg_spo2_median,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(75)], 2) AS p75_avg_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(95)], 2) AS p95_avg_spo2
FROM
  avg_spo2_per_stay;
