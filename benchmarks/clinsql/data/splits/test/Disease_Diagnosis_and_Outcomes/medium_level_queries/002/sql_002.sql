WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND p.anchor_age BETWEEN 50 AND 85
  ),
  diagnosis_flags AS (
    SELECT
      hadm_id,
      MAX(CASE
        WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I21', 'I22'))
        THEN 1 ELSE 0 END
      ) AS has_ami,
      MAX(CASE
        WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 4) = '7855')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'R57')
        THEN 1 ELSE 0 END
      ) AS has_shock,
      MAX(CASE
        WHEN (icd_version = 9 AND icd_code IN ('51881', '51882', '51884'))
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'J96')
        THEN 1 ELSE 0 END
      ) AS has_respiratory_failure,
      MAX(CASE
        WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '585')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'N18')
        THEN 1 ELSE 0 END
      ) AS has_ckd,
      MAX(CASE
        WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '250')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E13'))
        THEN 1 ELSE 0 END
      ) AS has_diabetes
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  final_cohort AS (
    SELECT
      b.hadm_id,
      b.hospital_expire_flag,
      d.has_ckd,
      d.has_diabetes,
      CASE
        WHEN b.length_of_stay <= 5 THEN 'le5_days'
        ELSE 'gt5_days'
      END AS los_group
    FROM
      base_admissions AS b
    INNER JOIN
      diagnosis_flags AS d
      ON b.hadm_id = d.hadm_id
    WHERE
      b.age_at_admission BETWEEN 62 AND 72
      AND d.has_ami = 1
      AND d.has_shock = 0
      AND d.has_respiratory_failure = 0
      AND b.length_of_stay > 0
  ),
  group_stats AS (
    SELECT
      los_group,
      COUNT(*) AS total_patients,
      SUM(hospital_expire_flag) AS in_hospital_deaths,
      SAFE_DIVIDE(SUM(hospital_expire_flag), COUNT(*)) AS mortality_rate,
      AVG(has_ckd) AS ckd_prevalence_rate,
      AVG(has_diabetes) AS diabetes_prevalence_rate
    FROM
      final_cohort
    GROUP BY
      los_group
  )
SELECT
  MAX(CASE WHEN los_group = 'le5_days' THEN total_patients END) AS patients_los_le5,
  MAX(CASE WHEN los_group = 'le5_days' THEN ROUND(mortality_rate * 100, 2) END) AS mortality_pct_los_le5,
  MAX(CASE WHEN los_group = 'le5_days' THEN ROUND(ckd_prevalence_rate * 100, 2) END) AS ckd_prevalence_pct_los_le5,
  MAX(CASE WHEN los_group = 'le5_days' THEN ROUND(diabetes_prevalence_rate * 100, 2) END) AS diabetes_prevalence_pct_los_le5,
  MAX(CASE WHEN los_group = 'gt5_days' THEN total_patients END) AS patients_los_gt5,
  MAX(CASE WHEN los_group = 'gt5_days' THEN ROUND(mortality_rate * 100, 2) END) AS mortality_pct_los_gt5,
  MAX(CASE WHEN los_group = 'gt5_days' THEN ROUND(ckd_prevalence_rate * 100, 2) END) AS ckd_prevalence_pct_los_gt5,
  MAX(CASE WHEN los_group = 'gt5_days' THEN ROUND(diabetes_prevalence_rate * 100, 2) END) AS diabetes_prevalence_pct_los_gt5,
  ROUND((MAX(CASE WHEN los_group = 'gt5_days' THEN mortality_rate END) - MAX(CASE WHEN los_group = 'le5_days' THEN mortality_rate END)) * 100, 2) AS abs_mortality_diff_pct_points,
  ROUND(SAFE_DIVIDE(
    MAX(CASE WHEN los_group = 'gt5_days' THEN mortality_rate END) - MAX(CASE WHEN los_group = 'le5_days' THEN mortality_rate END),
    MAX(CASE WHEN los_group = 'le5_days' THEN mortality_rate END)
  ) * 100, 2) AS rel_mortality_diff_percent
FROM
  group_stats;
