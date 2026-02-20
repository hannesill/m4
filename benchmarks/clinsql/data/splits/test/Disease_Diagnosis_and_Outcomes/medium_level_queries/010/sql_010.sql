WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 78 AND 88
  ),
  diagnosed_admissions AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I21', 'I22')) THEN 1
          ELSE 0
        END
      ) AS has_ami,
      MAX(
        CASE
          WHEN (icd_version = 9 AND icd_code IN ('51881', '51882', '51884'))
          OR (icd_version = 9 AND SUBSTR(icd_code, 1, 4) = '7855')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'J96')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'R57')
          THEN 1
          ELSE 0
        END
      ) AS has_exclusion
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  ami_cohort AS (
    SELECT
      b.subject_id,
      b.hadm_id,
      b.hospital_expire_flag,
      DATETIME_DIFF(b.dischtime, b.admittime, DAY) AS length_of_stay
    FROM
      base_admissions AS b
    JOIN
      diagnosed_admissions AS d
      ON b.hadm_id = d.hadm_id
    WHERE
      d.has_ami = 1
      AND d.has_exclusion = 0
      AND DATETIME_DIFF(b.dischtime, b.admittime, DAY) >= 0
  ),
  cohort_with_comorbidities AS (
    SELECT
      a.hadm_id,
      a.hospital_expire_flag,
      a.length_of_stay,
      COUNT(DISTINCT d.icd_code) AS comorbidity_count,
      MAX(
        CASE
          WHEN (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '585')
          OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) = 'N18') THEN 1
          ELSE 0
        END
      ) AS has_ckd,
      MAX(
        CASE
          WHEN (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '250')
          OR (
            d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E13')
          ) THEN 1
          ELSE 0
        END
      ) AS has_diabetes
    FROM
      ami_cohort AS a
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    GROUP BY
      a.hadm_id,
      a.hospital_expire_flag,
      a.length_of_stay
  ),
  stratified_data AS (
    SELECT
      hospital_expire_flag,
      has_ckd,
      has_diabetes,
      NTILE(4) OVER (ORDER BY length_of_stay) AS los_quartile,
      CASE
        WHEN comorbidity_count <= 10 THEN 'Low (<=10 diagnoses)'
        WHEN comorbidity_count BETWEEN 11 AND 20 THEN 'Medium (11-20 diagnoses)'
        ELSE 'High (>20 diagnoses)'
      END AS comorbidity_burden
    FROM
      cohort_with_comorbidities
  ),
  final_aggregation AS (
    SELECT
      los_quartile,
      comorbidity_burden,
      COUNT(*) AS total_patients,
      SUM(hospital_expire_flag) AS deaths,
      SAFE_DIVIDE(SUM(has_ckd), COUNT(*)) AS ckd_prevalence_ratio,
      SAFE_DIVIDE(SUM(has_diabetes), COUNT(*)) AS diabetes_prevalence_ratio
    FROM
      stratified_data
    GROUP BY
      los_quartile,
      comorbidity_burden
  )
SELECT
  los_quartile,
  comorbidity_burden,
  total_patients,
  deaths,
  ROUND(SAFE_DIVIDE(deaths, total_patients) * 100, 2) AS mortality_rate_percent,
  ROUND(
    (
      (
        SAFE_DIVIDE(deaths, total_patients) + (1.96 * 1.96) / (2 * total_patients) - 1.96 * SQRT(
          (
            SAFE_DIVIDE(deaths, total_patients) * (1 - SAFE_DIVIDE(deaths, total_patients))
            + (1.96 * 1.96) / (4 * total_patients)
          ) / total_patients
        )
      ) / (1 + (1.96 * 1.96) / total_patients)
    ) * 100,
    2
  ) AS mortality_ci_95_lower,
  ROUND(
    (
      (
        SAFE_DIVIDE(deaths, total_patients) + (1.96 * 1.96) / (2 * total_patients) + 1.96 * SQRT(
          (
            SAFE_DIVIDE(deaths, total_patients) * (1 - SAFE_DIVIDE(deaths, total_patients))
            + (1.96 * 1.96) / (4 * total_patients)
          ) / total_patients
        )
      ) / (1 + (1.96 * 1.96) / total_patients)
    ) * 100,
    2
  ) AS mortality_ci_95_upper,
  ROUND(ckd_prevalence_ratio * 100, 1) AS ckd_prevalence_percent,
  ROUND(diabetes_prevalence_ratio * 100, 1) AS diabetes_prevalence_percent
FROM
  final_aggregation
ORDER BY
  los_quartile,
  CASE
    WHEN comorbidity_burden LIKE 'Low%' THEN 1
    WHEN comorbidity_burden LIKE 'Medium%' THEN 2
    WHEN comorbidity_burden LIKE 'High%' THEN 3
  END;
