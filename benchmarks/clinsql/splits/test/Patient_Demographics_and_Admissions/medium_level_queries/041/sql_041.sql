WITH
  patient_cohort AS (
    SELECT
      a.hadm_id,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days,
      CASE
        WHEN a.hospital_expire_flag = 1
        THEN 'In-Hospital Mortality'
        WHEN a.discharge_location = 'HOME'
        THEN 'Discharged Home'
        WHEN a.discharge_location IN ('SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL')
        THEN 'Discharged to Facility'
      END AS discharge_outcome
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 88 AND 98
      AND a.admission_type = 'ELECTIVE'
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
  )
SELECT
  discharge_outcome,
  COUNT(*) AS number_of_patients,
  ROUND(AVG(length_of_stay_days), 1) AS mean_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_p50,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS percentile_75_los,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS percentile_90_los,
  ROUND(
    100 * (
      COUNTIF(length_of_stay_days <= 7) / COUNT(*)
    ),
    1
  ) AS percentile_rank_of_7_day_los
FROM
  patient_cohort
WHERE
  discharge_outcome IS NOT NULL
GROUP BY
  discharge_outcome
ORDER BY
  CASE
    WHEN discharge_outcome = 'Discharged Home' THEN 1
    WHEN discharge_outcome = 'Discharged to Facility' THEN 2
    WHEN discharge_outcome = 'In-Hospital Mortality' THEN 3
  END;
