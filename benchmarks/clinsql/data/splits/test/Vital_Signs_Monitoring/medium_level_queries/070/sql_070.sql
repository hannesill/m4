WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
      ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 90 AND 100
      AND ie.intime IS NOT NULL
  ),
  spo2_first_24h AS (
    SELECT
      cohort.stay_id,
      AVG(ce.valuenum) AS avg_spo2
    FROM
      patient_cohort AS cohort
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON cohort.stay_id = ce.stay_id
    WHERE
      ce.itemid = 220277
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 50 AND 100
      AND ce.charttime >= cohort.intime AND ce.charttime <= DATETIME_ADD(cohort.intime, INTERVAL 24 HOUR)
    GROUP BY
      cohort.stay_id
  ),
  aki_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE 'N17%'
      OR icd_code LIKE '584%'
  ),
  categorized_stays AS (
    SELECT
      s24.stay_id,
      cohort.hadm_id,
      s24.avg_spo2,
      CASE
        WHEN s24.avg_spo2 < 90 THEN '< 90%'
        WHEN s24.avg_spo2 >= 90 AND s24.avg_spo2 <= 92 THEN '90-92%'
        WHEN s24.avg_spo2 > 92 AND s24.avg_spo2 <= 95 THEN '93-95%'
        WHEN s24.avg_spo2 > 95 THEN '> 95%'
        ELSE 'Unknown'
      END AS spo2_category,
      CASE
        WHEN aki.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS aki_flag
    FROM
      spo2_first_24h AS s24
    INNER JOIN
      patient_cohort AS cohort
      ON s24.stay_id = cohort.stay_id
    LEFT JOIN
      aki_diagnoses AS aki
      ON cohort.hadm_id = aki.hadm_id
  )
SELECT
  spo2_category,
  COUNT(stay_id) AS number_of_stays,
  ROUND(AVG(avg_spo2), 2) AS mean_avg_spo2,
  ROUND(APPROX_QUANTILES(avg_spo2, 100)[OFFSET(50)], 2) AS median_avg_spo2,
  ROUND(
    APPROX_QUANTILES(avg_spo2, 100)[OFFSET(75)] - APPROX_QUANTILES(avg_spo2, 100)[OFFSET(25)],
    2
  ) AS iqr_avg_spo2,
  ROUND(
    100 * SAFE_DIVIDE(SUM(aki_flag), COUNT(stay_id)),
    2
  ) AS aki_rate_percent
FROM
  categorized_stays
WHERE
  spo2_category != 'Unknown'
GROUP BY
  spo2_category
ORDER BY
  CASE
    WHEN spo2_category = '< 90%' THEN 1
    WHEN spo2_category = '90-92%' THEN 2
    WHEN spo2_category = '93-95%' THEN 3
    WHEN spo2_category = '> 95%' THEN 4
  END;
