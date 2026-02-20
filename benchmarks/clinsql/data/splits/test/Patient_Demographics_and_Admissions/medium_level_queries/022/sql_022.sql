WITH patient_cohort AS (
  SELECT
    a.hadm_id,
    DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days,
    CASE
      WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
      WHEN a.discharge_location = 'HOME' THEN 'Discharged Home'
      WHEN a.discharge_location = 'HOSPICE' THEN 'Discharged to Hospice'
    END AS discharge_group
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 81 AND 91
    AND a.admission_location = 'TRANSFER FROM HOSPITAL'
    AND a.dischtime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
)
SELECT
  discharge_group,
  COUNT(*) AS number_of_patients,
  ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(25)] AS p25_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS p50_los_days_median,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS p75_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS p90_los_days,
  ROUND(
    100 * SAFE_DIVIDE(
      COUNTIF(length_of_stay_days <= 10),
      COUNT(*)
    ), 2
  ) AS percentile_rank_of_10_day_los
FROM
  patient_cohort
WHERE
  discharge_group IS NOT NULL
GROUP BY
  discharge_group
ORDER BY
  discharge_group;
