WITH
  icu_male_patients_in_age_range AS (
    SELECT DISTINCT
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.discharge_location,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON a.hadm_id = icu.hadm_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 38 AND 48
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
  ),
  los_with_outcomes AS (
    SELECT
      hadm_id,
      DATETIME_DIFF(dischtime, admittime, DAY) AS length_of_stay_days,
      CASE
        WHEN hospital_expire_flag = 1
        THEN 'In-Hospital Mortality'
        WHEN discharge_location = 'HOME'
        THEN 'Discharged Home'
        WHEN discharge_location IN (
          'SKILLED NURSING FACILITY',
          'REHAB/DISTINCT PART HOSP',
          'LONG TERM CARE HOSPITAL'
        )
        THEN 'Discharged to Facility'
        ELSE 'Other'
      END AS discharge_category
    FROM
      icu_male_patients_in_age_range
    WHERE
      DATETIME_DIFF(dischtime, admittime, DAY) > 0
  )
SELECT
  discharge_category,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(AVG(length_of_stay_days), 1) AS mean_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days_p50,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS percentile_75_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS percentile_90_los_days
FROM
  los_with_outcomes
WHERE
  discharge_category IN ('In-Hospital Mortality', 'Discharged Home', 'Discharged to Facility')
GROUP BY
  discharge_category
ORDER BY
  discharge_category;
