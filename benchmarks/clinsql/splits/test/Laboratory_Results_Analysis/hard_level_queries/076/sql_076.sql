WITH
lab_definitions AS (
  SELECT 50971 AS itemid, 'Potassium' AS label, 3.0 AS critical_low, 6.0 AS critical_high UNION ALL
  SELECT 50824 AS itemid, 'Potassium' AS label, 3.0 AS critical_low, 6.0 AS critical_high UNION ALL
  SELECT 50983 AS itemid, 'Sodium' AS label, 125 AS critical_low, 155 AS critical_high UNION ALL
  SELECT 50822 AS itemid, 'Sodium' AS label, 125 AS critical_low, 155 AS critical_high UNION ALL
  SELECT 50912 AS itemid, 'Creatinine' AS label, NULL AS critical_low, 2.5 AS critical_high UNION ALL
  SELECT 50806 AS itemid, 'Creatinine' AS label, NULL AS critical_low, 2.5 AS critical_high UNION ALL
  SELECT 51003 AS itemid, 'Troponin T' AS label, NULL AS critical_low, 0.1 AS critical_high UNION ALL
  SELECT 50931 AS itemid, 'Glucose' AS label, 60.0 AS critical_low, 400.0 AS critical_high UNION ALL
  SELECT 50809 AS itemid, 'Glucose' AS label, 60.0 AS critical_low, 400.0 AS critical_high UNION ALL
  SELECT 51006 AS itemid, 'BUN' AS label, NULL AS critical_low, 100.0 AS critical_high
),

acs_cohort AS (
  SELECT
    adm.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON adm.subject_id = pat.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON adm.hadm_id = dx.hadm_id
  WHERE
    pat.gender = 'M'
    AND (
      (dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code LIKE '411.1%'))
      OR (dx.icd_version = 10 AND (dx.icd_code LIKE 'I21%' OR dx.icd_code = 'I20.0'))
    )
  QUALIFY ROW_NUMBER() OVER(PARTITION BY adm.hadm_id ORDER BY dx.seq_num) = 1
),

filtered_acs_cohort AS (
  SELECT *
  FROM acs_cohort
  WHERE age_at_admission BETWEEN 87 AND 97
),

critical_events_72hr AS (
  SELECT
    le.hadm_id,
    def.label
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON le.hadm_id = adm.hadm_id
    INNER JOIN lab_definitions AS def
      ON le.itemid = def.itemid
  WHERE
    le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 72 HOUR)
    AND le.valuenum IS NOT NULL
    AND (
      (def.critical_low IS NOT NULL AND le.valuenum < def.critical_low)
      OR (def.critical_high IS NOT NULL AND le.valuenum > def.critical_high)
    )
),

cohort_instability_scores AS (
  SELECT
    fac.hadm_id,
    fac.hospital_expire_flag,
    DATETIME_DIFF(fac.dischtime, fac.admittime, DAY) AS los_days,
    COUNT(DISTINCT crit.label) AS instability_score
  FROM
    filtered_acs_cohort AS fac
    LEFT JOIN critical_events_72hr AS crit
      ON fac.hadm_id = crit.hadm_id
  GROUP BY
    fac.hadm_id,
    fac.hospital_expire_flag,
    fac.dischtime,
    fac.admittime
),

cohort_p95_score AS (
  SELECT
    APPROX_QUANTILES(instability_score, 100)[OFFSET(95)] AS p95_score
  FROM
    cohort_instability_scores
),

top_tier_cohort AS (
  SELECT
    score.hadm_id,
    score.los_days,
    score.hospital_expire_flag
  FROM
    cohort_instability_scores AS score
    CROSS JOIN cohort_p95_score AS p95
  WHERE
    score.instability_score >= p95.p95_score
),

top_tier_summary AS (
  SELECT
    AVG(los_days) AS avg_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_pct,
    COUNT(hadm_id) AS num_patients_in_top_tier
  FROM
    top_tier_cohort
),

comparison_rates AS (
  SELECT
    'Top_Tier_ACS_Cohort' AS group_name,
    SAFE_DIVIDE(
      CAST(COUNT(crit.hadm_id) AS FLOAT64),
      CAST(COUNT(DISTINCT ttc.hadm_id) AS FLOAT64)
    ) AS avg_critical_events_per_patient
  FROM top_tier_cohort AS ttc
  LEFT JOIN critical_events_72hr AS crit
    ON ttc.hadm_id = crit.hadm_id

  UNION ALL

  SELECT
    'General_Inpatient_Population' AS group_name,
    SAFE_DIVIDE(
      CAST((SELECT COUNT(*) FROM critical_events_72hr) AS FLOAT64),
      CAST((SELECT COUNT(DISTINCT le.hadm_id)
        FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
          ON le.hadm_id = adm.hadm_id
        WHERE le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 72 HOUR)) AS FLOAT64)
    ) AS avg_critical_events_per_patient
)

SELECT
  'P95 Instability Score (Target Cohort)' AS metric,
  CAST(p95.p95_score AS STRING) AS value,
  '95th percentile of the number of unique critically abnormal lab systems in the first 72h for male ACS patients aged 87-97.' AS description
FROM cohort_p95_score AS p95

UNION ALL

SELECT
  'Avg LOS (days) for Top Tier (>=P95)',
  CAST(ROUND(summary.avg_los_days, 2) AS STRING),
  CONCAT('Average length of stay for the ', CAST(summary.num_patients_in_top_tier AS STRING), ' patients in the top tier.')
FROM top_tier_summary AS summary

UNION ALL

SELECT
  'In-Hospital Mortality (%) for Top Tier (>=P95)',
  CAST(ROUND(summary.mortality_rate_pct, 2) AS STRING),
  CONCAT('In-hospital mortality rate for the ', CAST(summary.num_patients_in_top_tier AS STRING), ' patients in the top tier.')
FROM top_tier_summary AS summary

UNION ALL

SELECT
  'Avg Critical Lab Events per Patient (Top Tier)',
  CAST(ROUND(rates.avg_critical_events_per_patient, 2) AS STRING),
  'The average number of total critical lab events (not unique systems) per patient in the top-tier group within the first 72h.'
FROM comparison_rates AS rates
WHERE rates.group_name = 'Top_Tier_ACS_Cohort'

UNION ALL

SELECT
  'Avg Critical Lab Events per Patient (General Population)',
  CAST(ROUND(rates.avg_critical_events_per_patient, 2) AS STRING),
  'The average number of total critical lab events per patient in the general inpatient population within the first 72h.'
FROM comparison_rates AS rates
WHERE rates.group_name = 'General_Inpatient_Population';
