WITH
  cohort_stays AS (
    SELECT icu.stay_id, icu.intime
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON pat.subject_id = adm.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON adm.hadm_id = icu.hadm_id
    WHERE pat.gender = 'F'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 38 AND 48
      AND icu.intime IS NOT NULL
  ),
  sbp_first_24h AS (
    SELECT cs.stay_id, ce.valuenum
    FROM cohort_stays AS cs
    INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON cs.stay_id = ce.stay_id
    WHERE ce.itemid IN (220050, 51)
      AND ce.charttime BETWEEN cs.intime AND DATETIME_ADD(cs.intime, INTERVAL 24 HOUR)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0 AND ce.valuenum < 300
  ),
  avg_sbp_per_stay AS (
    SELECT stay_id, AVG(valuenum) AS avg_sbp
    FROM sbp_first_24h
    GROUP BY stay_id
  ),
  final_stats AS (
    SELECT
      'Female patients aged 38-48' AS cohort_description,
      COUNT(stay_id) AS total_icu_stays_in_cohort,
      ROUND(100 * (COUNTIF(avg_sbp < 120) / COUNT(stay_id)), 2) AS percentile_rank_of_sbp_120,
      ROUND(AVG(avg_sbp), 2) AS cohort_mean_avg_sbp,
      ROUND(STDDEV(avg_sbp), 2) AS cohort_stddev_avg_sbp,
      APPROX_QUANTILES(avg_sbp, 100) AS sbp_quantiles
    FROM avg_sbp_per_stay
  )
SELECT cohort_description, total_icu_stays_in_cohort, percentile_rank_of_sbp_120, cohort_mean_avg_sbp, cohort_stddev_avg_sbp,
  ROUND(sbp_quantiles[OFFSET(25)], 2) AS p25_avg_sbp,
  ROUND(sbp_quantiles[OFFSET(50)], 2) AS p50_avg_sbp_median,
  ROUND(sbp_quantiles[OFFSET(75)], 2) AS p75_avg_sbp
FROM final_stats;
