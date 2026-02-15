WITH
  icu_stays_in_scope AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 71 AND 81
      AND ie.intime IS NOT NULL
  ),
  temp_first_48h AS (
    SELECT
      s.stay_id,
      ce.valuenum AS temperature_c
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      icu_stays_in_scope AS s ON ce.stay_id = s.stay_id
    WHERE
      ce.itemid = 223762
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 32 AND 43
      AND DATETIME_DIFF(ce.charttime, s.intime, HOUR) BETWEEN 0 AND 48
  ),
  avg_temp_per_stay AS (
    SELECT
      stay_id,
      AVG(temperature_c) AS avg_temp_c
    FROM
      temp_first_48h
    GROUP BY
      stay_id
  ),
  categorized_stays AS (
    SELECT
      stay_id,
      avg_temp_c,
      CASE
        WHEN avg_temp_c < 36.0 THEN 'Hypothermic (<36.0 C)'
        WHEN avg_temp_c >= 36.0 AND avg_temp_c < 38.0 THEN 'Normothermic (36.0-37.9 C)'
        WHEN avg_temp_c >= 38.0 THEN 'Febrile (>=38.0 C)'
        ELSE NULL
      END AS temperature_category
    FROM
      avg_temp_per_stay
  ),
  mi_diagnoses AS (
    SELECT DISTINCT
      hadm_id,
      1 AS has_mi
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I21')
  ),
  final_cohort AS (
    SELECT
      cs.stay_id,
      cs.temperature_category,
      cs.avg_temp_c,
      COALESCE(mi.has_mi, 0) AS is_mi
    FROM
      categorized_stays AS cs
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON cs.stay_id = ie.stay_id
    LEFT JOIN
      mi_diagnoses AS mi ON ie.hadm_id = mi.hadm_id
    WHERE
      cs.temperature_category IS NOT NULL
  )
SELECT
  temperature_category,
  COUNT(stay_id) AS number_of_icu_stays,
  ROUND(AVG(avg_temp_c), 2) AS mean_avg_temp,
  ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(50)], 2) AS median_avg_temp,
  ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(25)], 2) AS p25_avg_temp,
  ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(75)], 2) AS p75_avg_temp,
  ROUND(
    APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(75)] - APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(25)], 2
  ) AS iqr_avg_temp,
  ROUND(AVG(is_mi) * 100, 2) AS mi_rate_percent
FROM
  final_cohort
GROUP BY
  temperature_category
ORDER BY
  CASE
    WHEN temperature_category = 'Hypothermic (<36.0 C)' THEN 1
    WHEN temperature_category = 'Normothermic (36.0-37.9 C)' THEN 2
    WHEN temperature_category = 'Febrile (>=38.0 C)' THEN 3
  END;
