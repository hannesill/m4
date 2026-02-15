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
      p.gender = 'M'
      AND p.anchor_age BETWEEN 43 AND 53
      AND a.admission_location = 'TRANSFER FROM HOSPITAL'
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
  ),
  discharge_categorization AS (
    SELECT
      length_of_stay_days,
      CASE
        WHEN hospital_expire_flag = 1
        THEN 'In-Hospital Mortality'
        WHEN discharge_location = 'HOME'
        THEN 'Discharged Home'
        WHEN
          discharge_location LIKE '%SKILLED NURSING FACILITY%'
          OR discharge_location LIKE '%REHAB%'
          OR discharge_location LIKE '%LONG TERM CARE HOSPITAL%'
        THEN 'Discharged to Facility'
        ELSE 'Other'
      END AS discharge_group
    FROM
      patient_cohort
  )
SELECT
  discharge_group,
  COUNT(*) AS patient_count,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days,
  (
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)]
    - APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(25)]
  ) AS iqr_los_days,
  ROUND(
    100 * SAFE_DIVIDE(
      COUNTIF(length_of_stay_days <= 10), COUNT(*)
    ),
    2
  ) AS percentile_rank_of_10_day_los
FROM
  discharge_categorization
WHERE
  discharge_group != 'Other'
GROUP BY
  discharge_group
ORDER BY
  median_los_days;
