WITH
  -- Step 1: Define the base cohort of male patients aged 51-61
  base_admissions AS (
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 51 AND 61
  ),
  -- Step 2: Filter for admissions with a diagnosis of postoperative complications
  postop_cohort AS (
    SELECT DISTINCT
      b.hadm_id,
      b.hospital_expire_flag,
      DATETIME_DIFF(b.dischtime, b.admittime, DAY) AS los_days
    FROM base_admissions AS b
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON b.hadm_id = d.hadm_id
    WHERE
      -- Filter for postoperative complication ICD codes
      (
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) IN ('996', '997', '998', '999'))
        OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'T80' AND 'T88')
      )
      -- Ensure LOS is at least 1 day to fit into the specified buckets
      AND DATETIME_DIFF(b.dischtime, b.admittime, DAY) >= 1
  ),
  -- Step 3: Stratify the cohort and add flags for prevalence metrics
  stratified_cohort AS (
    SELECT
      pc.hadm_id,
      pc.hospital_expire_flag,
      pc.los_days,
      -- Stratum 1: ICU vs Non-ICU
      CASE
        WHEN EXISTS (
          SELECT 1
          FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
          WHERE icu.hadm_id = pc.hadm_id
        )
        THEN 'ICU'
        ELSE 'Non-ICU'
      END AS icu_status,
      -- Stratum 2: Length of stay buckets
      CASE
        WHEN pc.los_days BETWEEN 1 AND 2 THEN '1-2 days'
        WHEN pc.los_days BETWEEN 3 AND 5 THEN '3-5 days'
        WHEN pc.los_days BETWEEN 6 AND 9 THEN '6-9 days'
        WHEN pc.los_days >= 10 THEN '>=10 days'
      END AS los_bucket,
      -- Stratum 3: Comorbidity buckets based on the count of Charlson conditions
      CASE
        WHEN COALESCE(
          ch.myocardial_infarct, 0) + COALESCE(ch.congestive_heart_failure, 0) + COALESCE(ch.peripheral_vascular_disease, 0) + COALESCE(ch.cerebrovascular_disease, 0) + COALESCE(ch.dementia, 0) + COALESCE(ch.chronic_pulmonary_disease, 0) + COALESCE(ch.rheumatic_disease, 0) + COALESCE(ch.peptic_ulcer_disease, 0) + COALESCE(ch.mild_liver_disease, 0) + COALESCE(ch.diabetes_without_cc, 0) + COALESCE(ch.diabetes_with_cc, 0) + COALESCE(ch.paraplegia, 0) + COALESCE(ch.renal_disease, 0) + COALESCE(ch.malignant_cancer, 0) + COALESCE(ch.severe_liver_disease, 0) + COALESCE(ch.metastatic_solid_tumor, 0) + COALESCE(ch.aids, 0
        ) <= 1 THEN '0-1 systems'
        WHEN COALESCE(
          ch.myocardial_infarct, 0) + COALESCE(ch.congestive_heart_failure, 0) + COALESCE(ch.peripheral_vascular_disease, 0) + COALESCE(ch.cerebrovascular_disease, 0) + COALESCE(ch.dementia, 0) + COALESCE(ch.chronic_pulmonary_disease, 0) + COALESCE(ch.rheumatic_disease, 0) + COALESCE(ch.peptic_ulcer_disease, 0) + COALESCE(ch.mild_liver_disease, 0) + COALESCE(ch.diabetes_without_cc, 0) + COALESCE(ch.diabetes_with_cc, 0) + COALESCE(ch.paraplegia, 0) + COALESCE(ch.renal_disease, 0) + COALESCE(ch.malignant_cancer, 0) + COALESCE(ch.severe_liver_disease, 0) + COALESCE(ch.metastatic_solid_tumor, 0) + COALESCE(ch.aids, 0
        ) = 2 THEN '2 systems'
        ELSE '>=3 systems'
      END AS comorbidity_bucket,
      -- Metric Flag: Chronic Kidney Disease (CKD)
      CASE
        WHEN EXISTS (
          SELECT 1
          FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
          WHERE
            d.hadm_id = pc.hadm_id
            AND (
              (d.icd_version = 9 AND d.icd_code LIKE '585%')
              OR (d.icd_version = 10 AND d.icd_code LIKE 'N18%')
            )
        )
        THEN 1
        ELSE 0
      END AS has_ckd,
      -- Metric Flag: Diabetes
      CASE
        WHEN EXISTS (
          SELECT 1
          FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
          WHERE
            d.hadm_id = pc.hadm_id
            AND (
              (d.icd_version = 9 AND d.icd_code LIKE '250%')
              OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E13'))
            )
        )
        THEN 1
        ELSE 0
      END AS has_diabetes
    FROM postop_cohort AS pc
    LEFT JOIN `physionet-data.mimiciv_3_1_derived.charlson` AS ch
      ON pc.hadm_id = ch.hadm_id
  ),
  -- Step 4: Create a grid of all possible strata combinations to ensure zero-count groups are included
  all_strata AS (
    SELECT
      icu_status,
      los_bucket,
      comorbidity_bucket
    FROM
      (SELECT 'ICU' AS icu_status UNION ALL SELECT 'Non-ICU')
    CROSS JOIN
      (
        SELECT '1-2 days' AS los_bucket
        UNION ALL
        SELECT '3-5 days'
        UNION ALL
        SELECT '6-9 days'
        UNION ALL
        SELECT '>=10 days'
      )
    CROSS JOIN
      (
        SELECT '0-1 systems' AS comorbidity_bucket
        UNION ALL
        SELECT '2 systems'
        UNION ALL
        SELECT '>=3 systems'
      )
  )
-- Step 5: Final aggregation to compute metrics for each stratum
SELECT
  s.icu_status,
  s.los_bucket,
  s.comorbidity_bucket,
  COUNT(sc.hadm_id) AS number_of_admissions,
  ROUND(SAFE_DIVIDE(SUM(sc.hospital_expire_flag), COUNT(sc.hadm_id)) * 100, 2) AS mortality_rate_pct,
  CAST(APPROX_QUANTILES(sc.los_days, 2)[OFFSET(1)] AS INT64) AS median_los_days,
  ROUND(SAFE_DIVIDE(SUM(sc.has_ckd), COUNT(sc.hadm_id)) * 100, 2) AS ckd_prevalence_pct,
  ROUND(SAFE_DIVIDE(SUM(sc.has_diabetes), COUNT(sc.hadm_id)) * 100, 2) AS diabetes_prevalence_pct
FROM all_strata AS s
LEFT JOIN stratified_cohort AS sc
  ON s.icu_status = sc.icu_status
  AND s.los_bucket = sc.los_bucket
  AND s.comorbidity_bucket = sc.comorbidity_bucket
GROUP BY
  s.icu_status,
  s.los_bucket,
  s.comorbidity_bucket
ORDER BY
  s.icu_status DESC,
  CASE s.los_bucket
    WHEN '1-2 days' THEN 1
    WHEN '3-5 days' THEN 2
    WHEN '6-9 days' THEN 3
    WHEN '>=10 days' THEN 4
  END,
  CASE s.comorbidity_bucket
    WHEN '0-1 systems' THEN 1
    WHEN '2 systems' THEN 2
    WHEN '>=3 systems' THEN 3
  END;
