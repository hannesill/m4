WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) BETWEEN 40 AND 50
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
  ),
  filtered_cohort AS (
    SELECT
      b.*
    FROM
      base_admissions AS b
    WHERE
      EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
        WHERE
          d.hadm_id = b.hadm_id
          AND (
            d.icd_code LIKE '410%'
            OR d.icd_code LIKE 'I21%'
            OR d.icd_code LIKE 'I22%'
          )
      )
      AND NOT EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
        WHERE
          d.hadm_id = b.hadm_id
          AND (
            d.icd_code LIKE '785.5%'
            OR d.icd_code LIKE 'R57%'
            OR d.icd_code IN ('518.81', '518.82', '518.84', '799.1')
            OR d.icd_code LIKE 'J96%'
            OR d.icd_code = 'R09.2'
          )
      )
  ),
  final_cohort_with_strata AS (
    SELECT
      fc.hadm_id,
      fc.hospital_expire_flag,
      fc.length_of_stay,
      CASE
        WHEN fc.length_of_stay <= 5 THEN '<= 5 days'
        ELSE '> 5 days'
      END AS los_group,
      CASE
        WHEN EXISTS (
          SELECT
            1
          FROM
            `physionet-data.mimiciv_3_1_icu.icustays` icu
          WHERE
            icu.hadm_id = fc.hadm_id
            AND icu.intime <= DATETIME_ADD(fc.admittime, INTERVAL 24 HOUR)
        ) THEN 'ICU on Day 1'
        ELSE 'Non-ICU on Day 1'
      END AS day1_icu_status
    FROM
      filtered_cohort AS fc
  )
SELECT
  los_group,
  day1_icu_status,
  COUNT(*) AS total_patients,
  SUM(hospital_expire_flag) AS total_deaths,
  ROUND(
    100.0 * SUM(hospital_expire_flag) / COUNT(*),
    2
  ) AS mortality_rate_percent,
  APPROX_QUANTILES(length_of_stay, 100) [OFFSET(50)] AS median_length_of_stay_days
FROM
  final_cohort_with_strata
GROUP BY
  los_group,
  day1_icu_status
ORDER BY
  los_group,
  day1_icu_status;
