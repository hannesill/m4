WITH
  patient_cohort AS (
    SELECT
      a.hadm_id,
      a.hospital_expire_flag,
      a.discharge_location,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 52 AND 62
      AND a.admission_type IN ('EW EMER', 'URGENT', 'DIRECT EMER', 'DIRECT OBSERVATION', 'OBSERVATION ADMIT')
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
  ),
  discharge_categorization AS (
    SELECT
      length_of_stay,
      CASE
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        WHEN UPPER(discharge_location) LIKE '%HOME%' THEN 'Discharged Home'
        WHEN
          UPPER(discharge_location) LIKE '%SKILLED NURSING%'
          OR UPPER(discharge_location) LIKE '%SNF%'
          OR UPPER(discharge_location) LIKE '%REHAB%'
          OR UPPER(discharge_location) LIKE '%LONG TERM CARE%'
          OR UPPER(discharge_location) LIKE '%LTACH%'
        THEN 'Discharged to Facility'
        ELSE 'Other'
      END AS discharge_group
    FROM
      patient_cohort
  )
SELECT
  discharge_group,
  COUNT(*) AS number_of_admissions,
  ROUND(AVG(length_of_stay), 2) AS mean_los_days,
  APPROX_QUANTILES(length_of_stay, 100)[OFFSET(50)] AS median_los_p50,
  APPROX_QUANTILES(length_of_stay, 100)[OFFSET(75)] AS los_p75,
  APPROX_QUANTILES(length_of_stay, 100)[OFFSET(90)] AS los_p90,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(length_of_stay <= 7),
      COUNT(*)
    ) * 100,
    1
  ) AS percentile_rank_of_7_days
FROM
  discharge_categorization
WHERE
  discharge_group IN ('In-Hospital Mortality', 'Discharged Home', 'Discharged to Facility')
GROUP BY
  discharge_group
ORDER BY
  discharge_group;
