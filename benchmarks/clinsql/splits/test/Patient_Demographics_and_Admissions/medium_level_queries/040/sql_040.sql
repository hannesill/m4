WITH surgical_hadm_ids AS (
  SELECT DISTINCT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.services`
  WHERE
    curr_service IN (
      'SURG',
      'CSURG',
      'NSURG',
      'TSURG',
      'VSURG',
      'ORTHO'
    )
),
patient_base AS (
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
    AND p.anchor_age BETWEEN 70 AND 80
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
),
categorized_patients AS (
  SELECT
    pb.hadm_id,
    CASE
      WHEN pb.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
      WHEN pb.discharge_location IN ('HOME', 'HOME HEALTH CARE') THEN 'Discharged Home'
      WHEN pb.discharge_location IN ('SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL') THEN 'Discharged to Facility'
      ELSE 'Other'
    END AS discharge_category,
    CASE WHEN pb.length_of_stay_days >= 7 THEN 1 ELSE 0 END AS los_ge_7_days_flag,
    CASE WHEN pb.length_of_stay_days >= 14 THEN 1 ELSE 0 END AS los_ge_14_days_flag
  FROM
    patient_base AS pb
  INNER JOIN
    surgical_hadm_ids AS s
    ON pb.hadm_id = s.hadm_id
)
SELECT
  discharge_category,
  COUNT(*) AS total_patients,
  SUM(los_ge_7_days_flag) AS count_los_ge_7_days,
  SUM(los_ge_14_days_flag) AS count_los_ge_14_days,
  ROUND((SUM(los_ge_7_days_flag) * 100.0) / COUNT(*), 2) AS proportion_los_ge_7_pct,
  ROUND((SUM(los_ge_14_days_flag) * 100.0) / COUNT(*), 2) AS proportion_los_ge_14_pct
FROM
  categorized_patients
WHERE
  discharge_category != 'Other'
GROUP BY
  discharge_category
ORDER BY
  discharge_category;
