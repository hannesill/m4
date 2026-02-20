WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      ie.stay_id,
      ie.intime,
      (p.anchor_age + EXTRACT(YEAR FROM ie.intime) - p.anchor_year) AS age_at_icustay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
      ON p.subject_id = ie.subject_id
    WHERE
      p.gender = 'F'
      AND ie.intime IS NOT NULL
  ),
  aged_patient_stays AS (
    SELECT
      stay_id,
      intime
    FROM
      patient_cohort
    WHERE
      age_at_icustay BETWEEN 87 AND 97
  ),
  spo2_first_24h AS (
    SELECT
      aps.stay_id,
      ce.valuenum AS spo2_value
    FROM
      aged_patient_stays AS aps
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON aps.stay_id = ce.stay_id
    WHERE
      ce.itemid = 220277
      AND DATETIME_DIFF(ce.charttime, aps.intime, HOUR) <= 24
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 70 AND 100
  ),
  avg_spo2_per_stay AS (
    SELECT
      stay_id,
      AVG(spo2_value) AS avg_spo2
    FROM
      spo2_first_24h
    GROUP BY
      stay_id
  )
SELECT
  'Female ICU Patients Aged 87-97 (First 24h Avg SpO2)' AS cohort_description,
  COUNT(stay_id) AS total_icu_stays_in_cohort,
  ROUND(AVG(avg_spo2), 2) AS mean_of_average_spo2,
  ROUND(STDDEV(avg_spo2), 2) AS stddev_of_average_spo2,
  ROUND(MIN(avg_spo2), 2) AS min_average_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(25)], 2) AS p25_average_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(50)], 2) AS p50_average_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(75)], 2) AS p75_average_spo2,
  ROUND(MAX(avg_spo2), 2) AS max_average_spo2,
  ROUND(
    100 * (
      (SELECT COUNT(*) FROM avg_spo2_per_stay WHERE avg_spo2 < 88.0) / (SELECT COUNT(*) FROM avg_spo2_per_stay)
    ),
    2
  ) AS percentile_rank_of_88_spo2
FROM
  avg_spo2_per_stay;
