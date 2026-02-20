WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    i.stay_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS i
    ON a.hadm_id = i.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 89 AND 99
), mi_diagnoses AS (
  SELECT DISTINCT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code LIKE '410%'
    OR icd_code LIKE 'I21%'
), temperature_measurements AS (
  SELECT
    pc.subject_id,
    pc.hadm_id,
    CASE
      WHEN ce.itemid = 223762 THEN ce.valuenum
      WHEN ce.itemid = 676 THEN (ce.valuenum - 32) * 5 / 9
    END AS temperature_celsius
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON pc.stay_id = ce.stay_id
  WHERE
    ce.itemid IN (223762, 676)
    AND ce.valuenum IS NOT NULL
), categorized_temps AS (
  SELECT
    tm.subject_id,
    tm.hadm_id,
    tm.temperature_celsius,
    CASE
      WHEN tm.temperature_celsius < 36.0 THEN 'Hypothermic (<36.0 C)'
      WHEN tm.temperature_celsius >= 36.0 AND tm.temperature_celsius < 38.0 THEN 'Normothermic (36.0-37.9 C)'
      WHEN tm.temperature_celsius >= 38.0 THEN 'Febrile (>=38.0 C)'
      ELSE NULL
    END AS temperature_category,
    CASE
      WHEN mi.hadm_id IS NOT NULL THEN 1
      ELSE 0
    END AS has_mi
  FROM
    temperature_measurements AS tm
  LEFT JOIN
    mi_diagnoses AS mi
    ON tm.hadm_id = mi.hadm_id
  WHERE
    tm.temperature_celsius BETWEEN 25 AND 45
)
SELECT
  ct.temperature_category,
  COUNT(DISTINCT ct.subject_id) AS unique_patient_count,
  COUNT(ct.temperature_celsius) AS measurement_count,
  ROUND(AVG(ct.temperature_celsius), 2) AS mean_temp_c,
  ROUND(APPROX_QUANTILES(ct.temperature_celsius, 100)[OFFSET(50)], 2) AS median_temp_c,
  ROUND(
    APPROX_QUANTILES(ct.temperature_celsius, 100)[OFFSET(75)] - APPROX_QUANTILES(ct.temperature_celsius, 100)[OFFSET(25)],
    2
  ) AS iqr_temp_c,
  COUNT(DISTINCT CASE WHEN ct.has_mi = 1 THEN ct.subject_id END) AS mi_patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT CASE WHEN ct.has_mi = 1 THEN ct.subject_id END) / COUNT(DISTINCT ct.subject_id),
    2
  ) AS mi_rate_percent
FROM
  categorized_temps AS ct
WHERE
  ct.temperature_category IS NOT NULL
GROUP BY
  ct.temperature_category
ORDER BY
  CASE
    WHEN ct.temperature_category = 'Hypothermic (<36.0 C)' THEN 1
    WHEN ct.temperature_category = 'Normothermic (36.0-37.9 C)' THEN 2
    WHEN ct.temperature_category = 'Febrile (>=38.0 C)' THEN 3
  END;
