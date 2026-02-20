WITH
  sepsis_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE 'A41%' OR icd_code = '99591'
  ),
  septic_shock_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code = 'R6521' OR icd_code = '78552'
  ),
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN sepsis_admissions AS s
      ON a.hadm_id = s.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 49 AND 59
      AND a.hadm_id NOT IN (SELECT hadm_id FROM septic_shock_admissions)
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
  ),
  cohort_with_features AS (
    SELECT
      b.hadm_id,
      b.hospital_expire_flag,
      CASE
        WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) <= 5 THEN '≤5 days'
        ELSE '>5 days'
      END AS los_group,
      CASE
        WHEN icu.stay_id IS NOT NULL THEN 'Day-1 ICU'
        ELSE 'Non-ICU'
      END AS day1_icu_status,
      CASE
        WHEN EXISTS (
          SELECT 1
          FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_ckd
          WHERE d_ckd.hadm_id = b.hadm_id
            AND (d_ckd.icd_code LIKE 'N18%' OR d_ckd.icd_code LIKE '585%')
        ) THEN 1
        ELSE 0
      END AS has_ckd,
      CASE
        WHEN EXISTS (
          SELECT 1
          FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_dm
          WHERE d_dm.hadm_id = b.hadm_id
            AND (
              d_dm.icd_code LIKE '250%'
              OR REGEXP_CONTAINS(d_dm.icd_code, r'^E(0[8-9]|1[0-1]|13)')
            )
        ) THEN 1
        ELSE 0
      END AS has_diabetes
    FROM base_cohort AS b
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON b.hadm_id = icu.hadm_id
      AND DATE(icu.intime) = DATE(b.admittime)
  )
SELECT
  los_group,
  day1_icu_status,
  COUNT(hadm_id) AS admission_count_N,
  SUM(hospital_expire_flag) AS total_deaths,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(has_ckd) * 100, 2) AS ckd_prevalence_pct,
  ROUND(AVG(has_diabetes) * 100, 2) AS diabetes_prevalence_pct
FROM cohort_with_features
GROUP BY
  los_group,
  day1_icu_status
ORDER BY
  los_group,
  day1_icu_status;
