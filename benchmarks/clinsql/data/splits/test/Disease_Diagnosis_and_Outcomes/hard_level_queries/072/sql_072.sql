WITH
  base_patients AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days,
      CASE
        WHEN p.dod IS NOT NULL AND p.dod <= DATE_ADD(a.admittime, INTERVAL 30 DAY)
        THEN 1
        ELSE 0
      END AS mortality_30_day_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 67 AND 77
  ),
  icu_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays`
  ),
  diagnosis_features AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN (icd_version = 10 AND icd_code LIKE 'I21%') OR (icd_version = 9 AND icd_code LIKE '410%')
          THEN 1
          ELSE 0
        END
      ) AS has_acs_flag,
      MAX(
        CASE
          WHEN (icd_version = 10 AND (icd_code LIKE 'I46%' OR icd_code LIKE 'I50%'))
          OR (icd_version = 9 AND (icd_code LIKE '427.5%' OR icd_code LIKE '428%'))
          THEN 1
          ELSE 0
        END
      ) AS has_cardiac_comp_flag,
      MAX(
        CASE
          WHEN (icd_version = 10 AND (icd_code LIKE 'I6%' OR icd_code = 'G93.1'))
          OR (icd_version = 9 AND icd_code LIKE '43%')
          THEN 1
          ELSE 0
        END
      ) AS has_neuro_comp_flag,
      COUNT(
        DISTINCT CASE
          WHEN (
            icd_version = 10 AND icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'J96.00', 'J80', 'Z51.11', 'R06.03', 'I46.9')
          )
          OR (
            icd_version = 9 AND icd_code IN ('995.92', '785.52', '038.9', '518.81', '518.82', 'V58.11', '786.03', '427.5')
          )
          OR (icd_version = 10 AND icd_code LIKE 'I21%')
          OR (icd_version = 9 AND icd_code LIKE '410%')
          THEN icd_code
        END
      ) AS critical_illness_dx_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  combined_cohort_data AS (
    SELECT
      bp.hadm_id,
      bp.los_days,
      bp.hospital_expire_flag,
      bp.mortality_30_day_flag,
      COALESCE(df.has_cardiac_comp_flag, 0) AS has_cardiac_comp_flag,
      COALESCE(df.has_neuro_comp_flag, 0) AS has_neuro_comp_flag,
      CASE
        WHEN df.has_acs_flag = 1 AND ia.hadm_id IS NOT NULL
        THEN 'Target: ACS Post-ICU (67-77F)'
        ELSE 'Control: General Inpatient (67-77F)'
      END AS cohort_group,
      LEAST(
        100,
        (COALESCE(df.critical_illness_dx_count, 0) * 15) + (COALESCE(df.has_cardiac_comp_flag, 0) * 10) + (COALESCE(df.has_neuro_comp_flag, 0) * 10)
      ) AS risk_score
    FROM
      base_patients AS bp
    LEFT JOIN
      diagnosis_features AS df ON bp.hadm_id = df.hadm_id
    LEFT JOIN
      icu_admissions AS ia ON bp.hadm_id = ia.hadm_id
    WHERE
      df.hadm_id IS NOT NULL
  ),
  target_profile_percentile AS (
    SELECT
      PERCENTILE_CONT(risk_score, 0.5) OVER () AS median_risk_score,
      PERCENT_RANK() OVER (ORDER BY risk_score) AS percentile_rank,
      risk_score
    FROM
      combined_cohort_data
    WHERE
      cohort_group = 'Target: ACS Post-ICU (67-77F)'
  )
SELECT
  ccd.cohort_group,
  COUNT(ccd.hadm_id) AS total_patients,
  ROUND(AVG(ccd.risk_score), 2) AS mean_risk_score,
  (
    SELECT
      ROUND(AVG(percentile_rank) * 100, 2)
    FROM
      target_profile_percentile
    WHERE
      risk_score = (
        SELECT
          CAST(ROUND(median_risk_score) AS INT64)
        FROM
          target_profile_percentile
        LIMIT 1
      )
  ) AS percentile_of_matched_profile,
  ROUND(AVG(ccd.mortality_30_day_flag) * 100, 2) AS mortality_30_day_rate_pct,
  ROUND(AVG(ccd.has_cardiac_comp_flag) * 100, 2) AS cardiac_complication_rate_pct,
  ROUND(AVG(ccd.has_neuro_comp_flag) * 100, 2) AS neurologic_complication_rate_pct,
  ROUND(AVG(CASE WHEN ccd.hospital_expire_flag = 0 THEN ccd.los_days ELSE NULL END), 2) AS survivor_mean_los_days
FROM
  combined_cohort_data AS ccd
GROUP BY
  ccd.cohort_group
ORDER BY
  mean_risk_score DESC;
