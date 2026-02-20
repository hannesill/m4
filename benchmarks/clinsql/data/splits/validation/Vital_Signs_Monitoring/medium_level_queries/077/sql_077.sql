WITH
  target_icu_stays AS (
    SELECT DISTINCT
      ie.stay_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON a.hadm_id = ie.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 42 AND 52
      AND ie.intime IS NOT NULL AND ie.outtime IS NOT NULL
  ),
  avg_hr_per_stay AS (
    SELECT
      ce.stay_id,
      AVG(ce.valuenum) AS avg_heart_rate
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    WHERE
      ce.stay_id IN (
        SELECT
          stay_id
        FROM
          target_icu_stays
      )
      AND ce.itemid IN (
        220045,
        211
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 20 AND 250
    GROUP BY
      ce.stay_id
  )
SELECT
  90 AS target_heart_rate_value,
  COUNT(*) AS total_icu_stays_in_cohort,
  SUM(CASE WHEN avg_heart_rate <= 90 THEN 1 ELSE 0 END) AS stays_at_or_below_target,
  ROUND(
    100.0 * SUM(CASE WHEN avg_heart_rate <= 90 THEN 1 ELSE 0 END) / COUNT(*),
    2
  ) AS percentile_rank_of_90_bpm,
  ROUND(AVG(avg_heart_rate), 2) AS cohort_mean_avg_hr,
  ROUND(STDDEV(avg_heart_rate), 2) AS cohort_stddev_avg_hr,
  APPROX_QUANTILES(avg_heart_rate, 100)[OFFSET(25)] AS p25_avg_hr,
  APPROX_QUANTILES(avg_heart_rate, 100)[OFFSET(50)] AS p50_median_avg_hr,
  APPROX_QUANTILES(avg_heart_rate, 100)[OFFSET(75)] AS p75_avg_hr
FROM
  avg_hr_per_stay;
