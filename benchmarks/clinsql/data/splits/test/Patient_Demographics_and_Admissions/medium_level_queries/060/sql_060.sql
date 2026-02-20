WITH
  patient_cohort AS (
    SELECT
      a.hadm_id,
      a.discharge_location,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 50 AND 60
      AND a.admission_location = 'EMERGENCY ROOM'
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
  ),
  outcome_categorization AS (
    SELECT
      length_of_stay_days,
      CASE
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        WHEN discharge_location = 'HOSPICE' THEN 'Discharged to Hospice'
        WHEN discharge_location LIKE 'HOME%' THEN 'Discharged Home'
        ELSE 'Other'
      END AS discharge_outcome
    FROM
      patient_cohort
  )
SELECT
  discharge_outcome,
  COUNT(*) AS number_of_admissions,
  ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
  ROUND(STDDEV(length_of_stay_days), 2) AS stddev_los_days,
  ROUND(
    100.0 * COUNTIF(length_of_stay_days <= 10) / COUNT(*),
    2
  ) AS percentile_rank_of_10_day_los
FROM
  outcome_categorization
WHERE
  discharge_outcome IN ('Discharged Home', 'Discharged to Hospice', 'In-Hospital Mortality')
GROUP BY
  discharge_outcome
ORDER BY
  mean_los_days DESC;
