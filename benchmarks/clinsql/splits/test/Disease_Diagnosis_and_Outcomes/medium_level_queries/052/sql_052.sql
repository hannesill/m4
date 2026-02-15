WITH
  base_cohort AS (
    SELECT
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 52 AND 62
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            d.icd_code LIKE '430%'
            OR d.icd_code LIKE '431%'
            OR d.icd_code LIKE '432%'
            OR d.icd_code LIKE '433%'
            OR d.icd_code LIKE '434%'
            OR d.icd_code LIKE 'I60%'
            OR d.icd_code LIKE 'I61%'
            OR d.icd_code LIKE 'I62%'
            OR d.icd_code LIKE 'I63%'
          )
      )
  ),
  cohort_features AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
      EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
        WHERE icu.hadm_id = c.hadm_id
      ) AS is_icu_admission,
      EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = c.hadm_id
          AND (d.icd_code LIKE '585%' OR d.icd_code LIKE 'N18%')
      ) AS has_ckd,
      EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = c.hadm_id
          AND (
            d.icd_code LIKE '250%'
            OR SUBSTR(d.icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E12', 'E13')
          )
      ) AS has_diabetes,
      (
        SELECT COUNT(DISTINCT d.icd_code)
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE d.hadm_id = c.hadm_id
      ) AS diagnosis_count
    FROM base_cohort AS c
  ),
  cohort_stratified AS (
    SELECT
      hadm_id,
      hospital_expire_flag,
      CAST(has_ckd AS INT64) AS has_ckd,
      CAST(has_diabetes AS INT64) AS has_diabetes,
      CASE
        WHEN is_icu_admission
        THEN 'ICU'
        ELSE 'Non-ICU'
      END AS icu_group,
      CASE
        WHEN los_days <= 5
        THEN '<=5 days'
        ELSE '>5 days'
      END AS los_bucket,
      CASE NTILE(3) OVER (ORDER BY diagnosis_count)
        WHEN 1
        THEN 'Low'
        WHEN 2
        THEN 'Medium'
        WHEN 3
        THEN 'High'
      END AS comorbidity_burden
    FROM cohort_features
  ),
  all_strata AS (
    SELECT
      icu_group,
      los_bucket,
      comorbidity_burden
    FROM
      (SELECT 'ICU' AS icu_group UNION ALL SELECT 'Non-ICU')
    CROSS JOIN (SELECT '<=5 days' AS los_bucket UNION ALL SELECT '>5 days')
    CROSS JOIN (
      SELECT 'Low' AS comorbidity_burden
      UNION ALL
      SELECT 'Medium'
      UNION ALL
      SELECT 'High'
    )
  ),
  grouped_data AS (
    SELECT
      icu_group,
      los_bucket,
      comorbidity_burden,
      COUNT(hadm_id) AS number_of_admissions,
      AVG(hospital_expire_flag) AS mortality_rate,
      AVG(has_ckd) AS ckd_prevalence,
      AVG(has_diabetes) AS diabetes_prevalence
    FROM cohort_stratified
    GROUP BY
      icu_group,
      los_bucket,
      comorbidity_burden
  )
SELECT
  s.icu_group,
  s.los_bucket,
  s.comorbidity_burden,
  COALESCE(g.number_of_admissions, 0) AS number_of_admissions,
  ROUND(COALESCE(g.mortality_rate, 0) * 100, 2) AS mortality_rate_percent,
  ROUND(COALESCE(g.ckd_prevalence, 0) * 100, 2) AS ckd_prevalence_percent,
  ROUND(COALESCE(g.diabetes_prevalence, 0) * 100, 2) AS diabetes_prevalence_percent
FROM all_strata AS s
LEFT JOIN grouped_data AS g
  ON s.icu_group = g.icu_group
  AND s.los_bucket = g.los_bucket
  AND s.comorbidity_burden = g.comorbidity_burden
ORDER BY
  s.icu_group DESC,
  s.los_bucket,
  CASE
    s.comorbidity_burden
    WHEN 'Low'
    THEN 1
    WHEN 'Medium'
    THEN 2
    WHEN 'High'
    THEN 3
  END;
