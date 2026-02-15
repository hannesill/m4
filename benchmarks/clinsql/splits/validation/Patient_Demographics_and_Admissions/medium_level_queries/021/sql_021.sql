WITH
  surgical_hadm_ids AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.services`
    WHERE
      curr_service IN ('SURG', 'TSURG', 'VSURG', 'NSURG', 'CSURG', 'TRAUM', 'ORTHO')
  ),
  patient_los_data AS (
    SELECT
      a.hadm_id,
      a.discharge_location,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 67 AND 77
      AND a.hadm_id IN (SELECT hadm_id FROM surgical_hadm_ids)
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 1
  ),
  discharge_groups AS (
    SELECT
      hadm_id,
      los_days,
      CASE
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        WHEN discharge_location IN ('HOME', 'HOME HEALTH CARE') THEN 'Discharged Home'
        WHEN discharge_location IN ('SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL') THEN 'Discharged to Facility'
        ELSE 'Other'
      END AS discharge_group
    FROM
      patient_los_data
  )
SELECT
  discharge_group,
  COUNT(hadm_id) AS num_admissions,
  ROUND(AVG(los_days), 2) AS mean_los,
  ROUND(STDDEV(los_days), 2) AS stddev_los,
  ROUND(
    100.0 * (
      COUNTIF(los_days <= 7) / COUNT(hadm_id)
    ),
    1
  ) AS percentile_rank_of_7_days
FROM
  discharge_groups
WHERE
  discharge_group != 'Other'
GROUP BY
  discharge_group
ORDER BY
  discharge_group;
