WITH
  male_patients_aged AS (
    SELECT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 82 AND 92
  ),
  icu_stays_filtered AS (
    SELECT
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
    INNER JOIN
      male_patients_aged AS mpa
      ON ie.hadm_id = mpa.hadm_id
    WHERE
      ie.intime IS NOT NULL
  ),
  first_24h_temps AS (
    SELECT
      isf.stay_id,
      ce.valuenum
    FROM
      icu_stays_filtered AS isf
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON isf.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (223762, 676)
      AND ce.valuenum IS NOT NULL
      AND ce.charttime BETWEEN isf.intime AND DATETIME_ADD(isf.intime, INTERVAL 24 HOUR)
      AND ce.valuenum BETWEEN 34 AND 42
  ),
  avg_temps_per_stay AS (
    SELECT
      stay_id,
      AVG(valuenum) AS avg_temp_c
    FROM
      first_24h_temps
    GROUP BY
      stay_id
  )
SELECT
  'Male ICU patients aged 82-92 (First 24h)' AS patient_population,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  COUNTIF(avg_temp_c <= 37.5) AS stays_with_avg_temp_lte_37_5,
  ROUND(100 * (COUNTIF(avg_temp_c <= 37.5) / COUNT(stay_id)), 1) AS percentile_rank_of_37_5_C,
  ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(25)], 2) AS p25_avg_temp_c,
  ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(50)], 2) AS p50_avg_temp_c_median,
  ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(75)], 2) AS p75_avg_temp_c,
  ROUND(AVG(avg_temp_c), 2) AS mean_avg_temp_c
FROM
  avg_temps_per_stay;
