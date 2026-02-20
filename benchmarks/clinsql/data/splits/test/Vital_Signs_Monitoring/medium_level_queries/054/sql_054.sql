WITH
  patient_stays AS (
    SELECT
      ie.stay_id,
      ie.intime,
      p.anchor_age + EXTRACT(YEAR FROM ie.intime) - p.anchor_year AS age_at_icustay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'F'
      AND ie.intime IS NOT NULL
  ),
  cohort_stays AS (
    SELECT
      stay_id,
      intime
    FROM
      patient_stays
    WHERE
      age_at_icustay BETWEEN 87 AND 97
  ),
  first_24hr_sbp AS (
    SELECT
      cs.stay_id,
      ce.valuenum
    FROM
      cohort_stays AS cs
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON cs.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (
        220050,
        51
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 40 AND 300
      AND DATETIME_DIFF(ce.charttime, cs.intime, HOUR) BETWEEN 0 AND 24
  ),
  avg_sbp_per_stay AS (
    SELECT
      stay_id,
      AVG(valuenum) AS avg_sbp
    FROM
      first_24hr_sbp
    GROUP BY
      stay_id
    HAVING
      COUNT(valuenum) > 0
  )
SELECT
  'Female patients aged 87-97' AS cohort_description,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  ROUND(100.0 * COUNTIF(avg_sbp < 150) / COUNT(stay_id), 2) AS percentile_rank_of_150_sbp,
  ROUND(AVG(avg_sbp), 2) AS mean_avg_sbp,
  ROUND(STDDEV(avg_sbp), 2) AS stddev_avg_sbp,
  ROUND(MIN(avg_sbp), 2) AS min_avg_sbp,
  ROUND(MAX(avg_sbp), 2) AS max_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(25)], 2) AS p25_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(50)], 2) AS p50_avg_sbp_median,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(75)], 2) AS p75_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(90)], 2) AS p90_avg_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp, 100)[OFFSET(95)], 2) AS p95_avg_sbp
FROM
  avg_sbp_per_stay;
