WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 83 AND 93
      AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL AND a.dischtime > a.admittime
  ),

  heart_failure_admissions AS (
    SELECT DISTINCT
      pc.hadm_id,
      pc.length_of_stay,
      pc.hospital_expire_flag
    FROM
      patient_cohort AS pc
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON pc.hadm_id = d.hadm_id
    WHERE
      (d.icd_code LIKE 'I50%' AND d.icd_version = 10)
      OR (d.icd_code LIKE '428%' AND d.icd_version = 9)
  ),

  comorbidity_flags AS (
    SELECT
      hfa.hadm_id,
      hfa.length_of_stay,
      hfa.hospital_expire_flag,
      MAX(CASE
          WHEN (d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%') AND d.icd_version = 10 THEN 1
          WHEN d.icd_code LIKE '250%' AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS diabetes_flag,
      MAX(CASE
          WHEN d.icd_code LIKE 'N18%' AND d.icd_version = 10 THEN 1
          WHEN d.icd_code LIKE '585%' AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS ckd_flag,
      MAX(CASE WHEN ((d.icd_code >= 'I10' AND d.icd_code < 'I17') OR (d.icd_code >= 'I20' AND d.icd_code < 'I26') OR (d.icd_code >= 'I47' AND d.icd_code < 'I50')) AND d.icd_version = 10 THEN 1
          WHEN ((d.icd_code >= '401' AND d.icd_code < '406') OR (d.icd_code >= '410' AND d.icd_code < '415') OR d.icd_code LIKE '427%') AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS cardiovascular_system,
      MAX(CASE WHEN ((d.icd_code >= 'E00' AND d.icd_code < 'E08') OR (d.icd_code >= 'E08' AND d.icd_code < 'E14') OR d.icd_code LIKE 'E66%' OR (d.icd_code >= 'E86' AND d.icd_code < 'E88')) AND d.icd_version = 10 THEN 1
          WHEN ((d.icd_code >= '240' AND d.icd_code < '247') OR d.icd_code LIKE '250%' OR d.icd_code LIKE '278.0%' OR d.icd_code LIKE '276%') AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS metabolic_system,
      MAX(CASE WHEN ((d.icd_code >= 'J12' AND d.icd_code < 'J19') OR d.icd_code LIKE 'J44%' OR d.icd_code LIKE 'J45%' OR d.icd_code LIKE 'J96%') AND d.icd_version = 10 THEN 1
          WHEN ((d.icd_code >= '480' AND d.icd_code < '487') OR d.icd_code LIKE '491%' OR d.icd_code LIKE '492%' OR d.icd_code = '496' OR d.icd_code LIKE '493%' OR d.icd_code IN ('518.81', '518.82', '518.84', '799.1')) AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS respiratory_system,
      MAX(CASE WHEN (d.icd_code LIKE 'N17%' OR d.icd_code LIKE 'N18%' OR d.icd_code LIKE 'N19%') AND d.icd_version = 10 THEN 1
          WHEN (d.icd_code LIKE '584%' OR d.icd_code LIKE '585%' OR d.icd_code LIKE '586%') AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS renal_system,
      MAX(CASE WHEN ((d.icd_code >= 'I60' AND d.icd_code < 'I70') OR (d.icd_code >= 'F01' AND d.icd_code < 'F04') OR d.icd_code LIKE 'G30%' OR (d.icd_code >= 'G40' AND d.icd_code < 'G42') OR d.icd_code LIKE 'R56%') AND d.icd_version = 10 THEN 1
          WHEN ((d.icd_code >= '430' AND d.icd_code < '439') OR d.icd_code LIKE '290%' OR d.icd_code LIKE '294.1%' OR d.icd_code LIKE '331.0%' OR d.icd_code LIKE '345%' OR d.icd_code LIKE '780.3%') AND d.icd_version = 9 THEN 1
          ELSE 0
      END) AS neurological_system
    FROM
      heart_failure_admissions AS hfa
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON hfa.hadm_id = d.hadm_id
    GROUP BY
      hfa.hadm_id, hfa.length_of_stay, hfa.hospital_expire_flag
  ),

  final_stratification AS (
    SELECT
      cf.hadm_id,
      cf.hospital_expire_flag,
      cf.length_of_stay,
      cf.diabetes_flag,
      cf.ckd_flag,
      CASE
        WHEN EXISTS (SELECT 1 FROM `physionet-data.mimiciv_3_1_icu.icustays` icu WHERE icu.hadm_id = cf.hadm_id)
          THEN 'Higher-Severity (ICU)'
        ELSE 'Lower-Severity (No ICU)'
      END AS severity_level,
      CASE
        WHEN cf.length_of_stay < 8 THEN '<8 days'
        ELSE '>=8 days'
      END AS los_group,
      CASE
        WHEN (cf.cardiovascular_system + cf.metabolic_system + cf.respiratory_system + cf.renal_system + cf.neurological_system) <= 1 THEN '0-1 Major Systems'
        WHEN (cf.cardiovascular_system + cf.metabolic_system + cf.respiratory_system + cf.renal_system + cf.neurological_system) = 2 THEN '2 Major Systems'
        ELSE '>=3 Major Systems'
      END AS comorbidity_group
    FROM
      comorbidity_flags AS cf
  )
SELECT
  severity_level,
  los_group,
  comorbidity_group,
  COUNT(hadm_id) AS total_admissions,
  SUM(hospital_expire_flag) AS in_hospital_deaths,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  APPROX_QUANTILES(length_of_stay, 2)[OFFSET(1)] AS median_los_days,
  ROUND(AVG(ckd_flag) * 100, 2) AS ckd_prevalence_pct,
  ROUND(AVG(diabetes_flag) * 100, 2) AS diabetes_prevalence_pct
FROM
  final_stratification
GROUP BY
  severity_level,
  los_group,
  comorbidity_group
ORDER BY
  CASE severity_level WHEN 'Higher-Severity (ICU)' THEN 1 ELSE 2 END,
  CASE los_group WHEN '<8 days' THEN 1 ELSE 2 END,
  CASE comorbidity_group
    WHEN '0-1 Major Systems' THEN 1
    WHEN '2 Major Systems' THEN 2
    ELSE 3
  END;
