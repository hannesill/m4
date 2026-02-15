WITH
  patient_cohort AS (
    SELECT
      a.hadm_id,
      a.hospital_expire_flag,
      a.discharge_location,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 80 AND 90
      AND a.admission_type NOT LIKE '%EMER%'
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
  ),
  categorized_admissions AS (
    SELECT
      length_of_stay_days,
      CASE
        WHEN hospital_expire_flag = 1
        THEN 'In-Hospital Mortality'
        WHEN UPPER(discharge_location) LIKE 'HOME%'
        THEN 'Discharged Home'
        WHEN UPPER(discharge_location) = 'HOSPICE'
        THEN 'Discharged to Hospice'
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
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS p90_los_days,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(length_of_stay_days <= 14),
      COUNT(*)
    ) * 100,
    2
  ) AS percentile_rank_of_14_days
FROM
  categorized_admissions
WHERE
  discharge_group IN ('In-Hospital Mortality', 'Discharged Home', 'Discharged to Hospice')
GROUP BY
  discharge_group
ORDER BY
  discharge_group;
