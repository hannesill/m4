WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.hospital_expire_flag,
      DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 35 AND 45
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
  ),
  icu_admissions AS (
    SELECT DISTINCT
      p.hadm_id,
      p.length_of_stay_days,
      p.hospital_expire_flag
    FROM
      patient_cohort AS p
    JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON p.hadm_id = icu.hadm_id
  )
SELECT
  CASE
    WHEN hospital_expire_flag = 1
    THEN 'In-Hospital Mortality'
    ELSE 'Discharged Alive'
  END AS survival_status,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
  ROUND(STDDEV(length_of_stay_days), 2) AS stddev_los_days,
  ROUND(
    100 * COUNTIF(length_of_stay_days < 7) / COUNT(hadm_id), 2
  ) AS percentile_rank_of_7_days
FROM
  icu_admissions
GROUP BY
  survival_status
ORDER BY
  survival_status;
