WITH
  icu_admissions AS (
    SELECT DISTINCT
      p.subject_id,
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
      p.gender = 'F'
      AND p.anchor_age BETWEEN 87 AND 97
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
  ),
  los_and_outcomes AS (
    SELECT
      hadm_id,
      DATE_DIFF(DATE(dischtime), DATE(admittime), DAY) AS length_of_stay,
      CASE
        WHEN hospital_expire_flag = 1
          THEN 'In-Hospital Mortality'
        WHEN discharge_location = 'HOME'
          THEN 'Discharged Home'
        WHEN discharge_location IN (
          'SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL'
        )
          THEN 'Discharged to Facility'
        ELSE 'Other'
      END AS discharge_group
    FROM
      icu_admissions
  )
SELECT
  discharge_group,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(AVG(length_of_stay), 2) AS mean_los_days,
  ROUND(STDDEV(length_of_stay), 2) AS stddev_los_days,
  ROUND(
    100.0 * COUNTIF(length_of_stay < 10) / COUNT(hadm_id), 2
  ) AS percentile_rank_of_10_day_los
FROM
  los_and_outcomes
WHERE
  discharge_group != 'Other'
  AND length_of_stay >= 0
GROUP BY
  discharge_group
ORDER BY
  mean_los_days DESC;
