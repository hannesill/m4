WITH base_admissions AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
),

sepsis_diagnoses AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code IN (
      '99591',
      'R6520'
    ) OR icd_code LIKE 'A41%'
),

septic_shock_diagnoses AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code IN (
      '78552',
      'R6521'
    )
),

final_cohort_with_features AS (
  SELECT
    adm.hadm_id,
    adm.hospital_expire_flag,
    DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS length_of_stay,
    CASE
      WHEN DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) <= 7 THEN '≤7 days'
      ELSE '>7 days'
    END AS los_group,
    CASE
      WHEN EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
        WHERE icu.hadm_id = adm.hadm_id
          AND DATETIME_DIFF(icu.intime, adm.admittime, HOUR) <= 24
      ) THEN 'ICU Day 1'
      ELSE 'Non-ICU Day 1'
    END AS day1_icu_status
  FROM
    base_admissions AS adm
  WHERE
    adm.hadm_id IN (SELECT hadm_id FROM sepsis_diagnoses)
    AND adm.hadm_id NOT IN (SELECT hadm_id FROM septic_shock_diagnoses)
)

SELECT
  los_group,
  day1_icu_status,
  COUNT(hadm_id) AS total_admissions,
  SUM(hospital_expire_flag) AS total_deaths,
  ROUND(100.0 * SUM(hospital_expire_flag) / COUNT(hadm_id), 2) AS mortality_rate_percent,
  APPROX_QUANTILES(length_of_stay, 2)[OFFSET(1)] AS median_length_of_stay_days
FROM
  final_cohort_with_features
GROUP BY
  los_group,
  day1_icu_status
ORDER BY
  los_group,
  day1_icu_status;
