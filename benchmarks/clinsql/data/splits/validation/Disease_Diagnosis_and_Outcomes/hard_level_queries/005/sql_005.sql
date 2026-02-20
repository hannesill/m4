WITH
  admissions_with_age AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.dod,
      p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 43 AND 53
  ),
  icd_flags AS (
    SELECT
      hadm_id,
      MAX(CASE
          WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '428') THEN 1
          WHEN (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I50') THEN 1
          ELSE 0
        END) AS is_hf,
      MAX(CASE
          WHEN (icd_version = 10 AND icd_code IN ('R68.81', 'R57.0')) OR (icd_version = 9 AND icd_code IN ('995.92', '785.52')) THEN 1
          ELSE 0
        END) AS is_multi_organ_failure,
      MAX(CASE
          WHEN (icd_version = 10 AND icd_code IN ('R65.21', 'A41.9')) OR (icd_version = 9 AND icd_code IN ('995.92', '038.9')) THEN 1
          ELSE 0
        END) AS is_septic_shock,
      MAX(CASE
          WHEN (icd_version = 10 AND (SUBSTR(icd_code, 1, 3) = 'I21' OR icd_code = 'I46.9')) OR (icd_version = 9 AND (SUBSTR(icd_code, 1, 3) = '410' OR icd_code = '427.5')) THEN 1
          ELSE 0
        END) AS is_acute_mi,
      MAX(CASE
          WHEN (icd_version = 10 AND icd_code IN ('J96.00', 'J80')) OR (icd_version = 9 AND icd_code IN ('518.81', '518.82')) THEN 1
          ELSE 0
        END) AS is_resp_failure,
      COUNT(DISTINCT icd_code) AS num_total_diagnoses
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  icu_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_icu.icustays`
  ),
  final_data_with_scores AS (
    SELECT
      aa.hadm_id,
      aa.hospital_expire_flag,
      CASE
        WHEN icd.is_hf = 1 AND icu.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS is_target_cohort,
      LEAST(100,
        (icd.is_multi_organ_failure * 25) +
        (icd.is_septic_shock * 25) +
        (icd.is_acute_mi * 20) +
        (icd.is_resp_failure * 20) +
        (icd.num_total_diagnoses * 0.5)
      ) AS risk_score,
      CASE
        WHEN aa.dod IS NOT NULL AND DATE_DIFF(DATE(aa.dod), DATE(aa.admittime), DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS mortality_30_day,
      GREATEST(icd.is_multi_organ_failure, icd.is_septic_shock, icd.is_acute_mi, icd.is_resp_failure) AS has_major_complication,
      DATETIME_DIFF(aa.dischtime, aa.admittime, DAY) AS los_days
    FROM
      admissions_with_age AS aa
    INNER JOIN
      icd_flags AS icd ON aa.hadm_id = icd.hadm_id
    LEFT JOIN
      icu_admissions AS icu ON aa.hadm_id = icu.hadm_id
  ),
  target_cohort_stats AS (
    SELECT
      'Target: Females 43-53, HF, Post-ICU' AS cohort_name,
      COUNT(*) AS total_patients,
      APPROX_QUANTILES(risk_score, 100)[OFFSET(50)] AS median_risk_score,
      APPROX_QUANTILES(risk_score, 100)[OFFSET(75)] - APPROX_QUANTILES(risk_score, 100)[OFFSET(25)] AS iqr_risk_score,
      AVG(mortality_30_day) * 100 AS mortality_30_day_rate_pct,
      AVG(has_major_complication) * 100 AS major_complication_rate_pct,
      AVG(CASE WHEN hospital_expire_flag = 0 THEN los_days END) AS survivor_los_avg_days,
      AVG(risk_score) AS avg_risk_score
    FROM
      final_data_with_scores
    WHERE
      is_target_cohort = 1
  ),
  general_population_stats AS (
    SELECT
      'Comparison: All Females 43-53' AS cohort_name,
      COUNT(*) AS total_patients,
      AVG(has_major_complication) * 100 AS major_complication_rate_pct,
      AVG(CASE WHEN hospital_expire_flag = 0 THEN los_days END) AS survivor_los_avg_days
    FROM
      final_data_with_scores
  ),
  percentile_rank_calc AS (
    SELECT
      100 * (
        SELECT COUNTIF(risk_score < (SELECT avg_risk_score FROM target_cohort_stats))
        FROM final_data_with_scores
      ) / (
        SELECT COUNT(risk_score)
        FROM final_data_with_scores
      ) AS risk_score_percentile_rank
  )
SELECT
  tcs.cohort_name,
  tcs.total_patients,
  ROUND(tcs.median_risk_score, 2) AS median_risk_score,
  ROUND(tcs.iqr_risk_score, 2) AS iqr_risk_score,
  ROUND(tcs.mortality_30_day_rate_pct, 2) AS mortality_30_day_rate_pct,
  ROUND(tcs.major_complication_rate_pct, 2) AS major_complication_rate_pct,
  ROUND(tcs.survivor_los_avg_days, 1) AS survivor_los_avg_days,
  ROUND(prc.risk_score_percentile_rank, 1) AS risk_percentile_of_matched_profile
FROM
  target_cohort_stats AS tcs
CROSS JOIN
  percentile_rank_calc AS prc
UNION ALL
SELECT
  gps.cohort_name,
  gps.total_patients,
  NULL AS median_risk_score,
  NULL AS iqr_risk_score,
  NULL AS mortality_30_day_rate_pct,
  ROUND(gps.major_complication_rate_pct, 2) AS major_complication_rate_pct,
  ROUND(gps.survivor_los_avg_days, 1) AS survivor_los_avg_days,
  NULL AS risk_percentile_of_matched_profile
FROM
  general_population_stats AS gps;
