WITH
  patient_base AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.dischtime,
      a.admittime,
      a.discharge_location,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 40 AND 50
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND a.dischtime > a.admittime
  ),
  icu_cohort AS (
    SELECT DISTINCT
      b.hadm_id,
      b.discharge_location,
      b.hospital_expire_flag,
      DATETIME_DIFF(b.dischtime, b.admittime, DAY) AS los_days
    FROM
      patient_base AS b
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON b.hadm_id = icu.hadm_id
  ),
  discharge_stratification AS (
    SELECT
      los_days,
      CASE
        WHEN hospital_expire_flag = 1
        THEN 'In-Hospital Mortality'
        WHEN UPPER(discharge_location) LIKE '%HOSPICE%'
        THEN 'Discharged to Hospice'
        WHEN UPPER(discharge_location) IN ('HOME', 'HOME HEALTH CARE')
        THEN 'Discharged Home'
      END AS discharge_outcome
    FROM
      icu_cohort
  )
SELECT
  discharge_outcome,
  COUNT(*) AS total_patients,
  APPROX_QUANTILES(los_days, 100)[OFFSET(50)] AS p50_los_days,
  APPROX_QUANTILES(los_days, 100)[OFFSET(75)] AS p75_los_days,
  APPROX_QUANTILES(los_days, 100)[OFFSET(90)] AS p90_los_days,
  APPROX_QUANTILES(los_days, 100)[OFFSET(95)] AS p95_los_days,
  ROUND(100 * SAFE_DIVIDE(COUNTIF(los_days <= 7), COUNT(los_days)), 2) AS percentile_rank_of_7_days
FROM
  discharge_stratification
WHERE
  discharge_outcome IS NOT NULL
GROUP BY
  discharge_outcome
ORDER BY
  discharge_outcome;
