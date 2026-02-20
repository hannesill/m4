WITH
patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
    a.admittime,
    a.dischtime,
    p.dod,
    a.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 80 AND 90
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
),
acute_hf_admissions AS (
  SELECT DISTINCT
    pc.hadm_id,
    pc.subject_id,
    pc.admittime,
    pc.dischtime,
    pc.dod,
    pc.hospital_expire_flag
  FROM
    patient_cohort AS pc
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON pc.hadm_id = d.hadm_id
  WHERE
    d.icd_code IN (
      '4280',
      '42821',
      '42823',
      '42831',
      '42833',
      '42841',
      '42843',
      'I509',
      'I5021',
      'I5023',
      'I5031',
      'I5033',
      'I5041',
      'I5043'
    )
),
los_data AS (
  SELECT
    hadm_id,
    hospital_expire_flag,
    CASE
      WHEN hospital_expire_flag = 1 THEN DATETIME_DIFF(dod, admittime, DAY)
      ELSE NULL
    END AS time_to_death_days,
    CASE
      WHEN DATETIME_DIFF(dischtime, admittime, DAY) BETWEEN 0 AND 3 THEN '1-3 days'
      WHEN DATETIME_DIFF(dischtime, admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 days'
      WHEN DATETIME_DIFF(dischtime, admittime, DAY) >= 8 THEN '>=8 days'
      ELSE 'Other'
    END AS los_category
  FROM
    acute_hf_admissions
)
SELECT
  los_category,
  COUNT(hadm_id) AS total_admissions,
  SUM(hospital_expire_flag) AS in_hospital_deaths,
  ROUND(100.0 * SUM(hospital_expire_flag) / COUNT(hadm_id), 2) AS mortality_rate_percent,
  ROUND(
    100.0 * (
      (SUM(hospital_expire_flag) / COUNT(hadm_id))
      - 1.96 * SAFE.SQRT(
          (SUM(hospital_expire_flag) / COUNT(hadm_id))
          * (1 - (SUM(hospital_expire_flag) / COUNT(hadm_id)))
          / COUNT(hadm_id)
        )
    ), 2
  ) AS mortality_ci_95_lower,
  ROUND(
    100.0 * (
      (SUM(hospital_expire_flag) / COUNT(hadm_id))
      + 1.96 * SAFE.SQRT(
          (SUM(hospital_expire_flag) / COUNT(hadm_id))
          * (1 - (SUM(hospital_expire_flag) / COUNT(hadm_id)))
          / COUNT(hadm_id)
        )
    ), 2
  ) AS mortality_ci_95_upper,
  APPROX_QUANTILES(time_to_death_days, 2 IGNORE NULLS)[OFFSET(1)] AS median_time_to_death_days_for_deceased
FROM
  los_data
WHERE
  los_category != 'Other'
GROUP BY
  los_category
ORDER BY
  CASE
    WHEN los_category = '1-3 days' THEN 1
    WHEN los_category = '4-7 days' THEN 2
    WHEN los_category = '>=8 days' THEN 3
  END;
