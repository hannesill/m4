WITH
  cohort_diagnoses AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND (
          STARTS_WITH(icd_code, '570')
          OR STARTS_WITH(icd_code, '572.2')
          OR STARTS_WITH(icd_code, '572.4')
      )) OR
      (icd_version = 10 AND (
          STARTS_WITH(icd_code, 'K72')
          OR STARTS_WITH(icd_code, 'K71.11')
          OR STARTS_WITH(icd_code, 'K76.7')
      ))
  ),
  target_cohort AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON adm.subject_id = pat.subject_id
    INNER JOIN cohort_diagnoses AS dx
      ON adm.hadm_id = dx.hadm_id
    WHERE
      pat.gender = 'M'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 75 AND 85
  ),
  lab_definitions AS (
    SELECT 'Bilirubin' AS lab_name, 50885 AS itemid, NULL AS critical_low, 12.0 AS critical_high UNION ALL
    SELECT 'ALT' AS lab_name, 50861 AS itemid, NULL AS critical_low, 1000.0 AS critical_high UNION ALL
    SELECT 'AST' AS lab_name, 50878 AS itemid, NULL AS critical_low, 1000.0 AS critical_high UNION ALL
    SELECT 'INR' AS lab_name, 51237 AS itemid, NULL AS critical_low, 5.0 AS critical_high UNION ALL
    SELECT 'Creatinine' AS lab_name, 50912 AS itemid, NULL AS critical_low, 4.0 AS critical_high UNION ALL
    SELECT 'Lactate' AS lab_name, 50813 AS itemid, NULL AS critical_low, 4.0 AS critical_high UNION ALL
    SELECT 'Platelets' AS lab_name, 51265 AS itemid, 50.0 AS critical_low, NULL AS critical_high
  ),
  all_labs_first_48h AS (
    SELECT
      le.hadm_id,
      le.itemid,
      le.valuenum,
      CASE WHEN tc.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS is_cohort_member
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON le.hadm_id = adm.hadm_id
    LEFT JOIN target_cohort AS tc
      ON le.hadm_id = tc.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND le.itemid IN (SELECT itemid FROM lab_definitions)
      AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 48 HOUR)
  ),
  critical_events AS (
    SELECT
      labs.hadm_id,
      def.lab_name,
      labs.is_cohort_member,
      CASE
        WHEN (def.critical_low IS NOT NULL AND labs.valuenum < def.critical_low)
          OR (def.critical_high IS NOT NULL AND labs.valuenum > def.critical_high)
        THEN 1
        ELSE 0
      END AS is_critical
    FROM all_labs_first_48h AS labs
    INNER JOIN lab_definitions AS def
      ON labs.itemid = def.itemid
  ),
  instability_score_cohort AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT CASE WHEN is_critical = 1 THEN lab_name END) AS instability_score
    FROM critical_events
    WHERE is_cohort_member = 1
    GROUP BY hadm_id
  ),
  cohort_summary AS (
    SELECT
      MAX(COALESCE(scores.instability_score, 0)) AS max_instability_score,
      APPROX_QUANTILES(COALESCE(scores.instability_score, 0), 100)[OFFSET(25)] AS p25_instability_score,
      APPROX_QUANTILES(COALESCE(scores.instability_score, 0), 100)[OFFSET(50)] AS p50_instability_score,
      APPROX_QUANTILES(COALESCE(scores.instability_score, 0), 100)[OFFSET(75)] AS p75_instability_score,
      APPROX_QUANTILES(COALESCE(scores.instability_score, 0), 100)[OFFSET(90)] AS p90_instability_score,
      AVG(DATETIME_DIFF(cohort.dischtime, cohort.admittime, DAY)) AS avg_los_days,
      AVG(CAST(cohort.hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent,
      COUNT(DISTINCT cohort.hadm_id) as cohort_size
    FROM target_cohort AS cohort
    LEFT JOIN instability_score_cohort AS scores
      ON cohort.hadm_id = scores.hadm_id
  ),
  critical_frequency_comparison AS (
    SELECT
      lab_name,
      SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN is_cohort_member = 1 AND is_critical = 1 THEN hadm_id END),
        COUNT(DISTINCT CASE WHEN is_cohort_member = 1 THEN hadm_id END)
      ) * 100 AS cohort_critical_frequency_percent,
      SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN is_critical = 1 AND is_cohort_member = 0 THEN hadm_id END),
        COUNT(DISTINCT CASE WHEN is_cohort_member = 0 THEN hadm_id END)
      ) * 100 AS general_population_critical_frequency_percent,
      COUNT(DISTINCT CASE WHEN is_cohort_member = 1 THEN hadm_id END) as cohort_patients_with_lab,
      COUNT(DISTINCT CASE WHEN is_cohort_member = 0 THEN hadm_id END) as general_patients_with_lab
    FROM critical_events
    GROUP BY lab_name
  )
SELECT
  metric.sort_key,
  metric.metric_type,
  metric.metric_name,
  metric.value,
  metric.description,
  summary.cohort_size
FROM cohort_summary AS summary,
UNNEST([
  STRUCT(1 AS sort_key, 'COHORT_SUMMARY' AS metric_type, 'Cohort Size' AS metric_name, CAST(summary.cohort_size AS STRING) AS value, 'Total number of patients in the target cohort.' AS description),
  STRUCT(2, 'COHORT_SUMMARY', 'In-Hospital Mortality Rate (%)', FORMAT('%.2f', summary.mortality_rate_percent), 'Percentage of patients in the cohort who died during the hospital admission.'),
  STRUCT(3, 'COHORT_SUMMARY', 'Average Length of Stay (Days)', FORMAT('%.2f', summary.avg_los_days), 'Average hospital length of stay for the cohort.'),
  STRUCT(4, 'COHORT_SUMMARY', 'Maximum Instability Score', CAST(summary.max_instability_score AS STRING), 'The highest number of unique critical lab derangements for any single patient in the cohort.'),
  STRUCT(5, 'COHORT_SUMMARY', 'Instability Score Percentiles (25th, 50th, 75th, 90th)', CONCAT('P25: ', CAST(summary.p25_instability_score AS STRING), ', P50: ', CAST(summary.p50_instability_score AS STRING), ', P75: ', CAST(summary.p75_instability_score AS STRING), ', P90: ', CAST(summary.p90_instability_score AS STRING)), 'Distribution of the instability score across the cohort.')
]) AS metric
UNION ALL
SELECT
  6 AS sort_key,
  'CRITICAL_FREQUENCY' AS metric_type,
  lab_name AS metric_name,
  CONCAT(
    'Cohort: ', FORMAT('%.2f', cohort_critical_frequency_percent), '%',
    ' vs. General: ', FORMAT('%.2f', general_population_critical_frequency_percent), '%'
  ) AS value,
  CONCAT(
      'Comparison of critical event frequency. Cohort N=', CAST(cohort_patients_with_lab AS STRING),
      ', General N=', CAST(general_patients_with_lab AS STRING),
      ' (N=patients with this lab drawn in first 48h).'
  ) AS description,
  NULL as cohort_size
FROM critical_frequency_comparison
ORDER BY sort_key, metric_name;
