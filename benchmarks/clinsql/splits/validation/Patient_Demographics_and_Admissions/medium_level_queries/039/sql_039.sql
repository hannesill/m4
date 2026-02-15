WITH
  patient_cohort AS (
    SELECT
      a.hadm_id,
      a.discharge_location,
      a.hospital_expire_flag,
      GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 37 AND 47
      AND a.admission_type IN ('URGENT', 'EW EMER.')
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
  ),
  cohort_with_outcome AS (
    SELECT
      length_of_stay_days,
      CASE
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        WHEN discharge_location = 'HOME' THEN 'Discharged Home'
        WHEN discharge_location IN (
          'SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL'
        ) THEN 'Discharged to Facility'
        ELSE 'Other'
      END AS discharge_group
    FROM
      patient_cohort
  )
SELECT
  discharge_group,
  COUNT(*) AS total_admissions,
  ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(25)] AS p25_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS p75_los_days,
  ROUND(
    100 * (
      COUNTIF(length_of_stay_days <= 7) / COUNT(*)
    ),
    1
  ) AS percentile_rank_of_7_days
FROM
  cohort_with_outcome
WHERE
  discharge_group != 'Other'
GROUP BY
  discharge_group
ORDER BY
  discharge_group;
