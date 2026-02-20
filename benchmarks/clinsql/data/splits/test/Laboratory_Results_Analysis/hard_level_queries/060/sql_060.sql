WITH
  lab_definitions AS (
    SELECT * FROM UNNEST([
      STRUCT('Potassium' AS lab_name, 50971 AS itemid, 2.5 AS critical_low, 6.5 AS critical_high),
      STRUCT('Potassium' AS lab_name, 50822 AS itemid, 2.5 AS critical_low, 6.5 AS critical_high),
      STRUCT('Sodium' AS lab_name, 50983 AS itemid, 120.0 AS critical_low, 160.0 AS critical_high),
      STRUCT('Sodium' AS lab_name, 50824 AS itemid, 120.0 AS critical_low, 160.0 AS critical_high),
      STRUCT('Lactate' AS lab_name, 50813 AS itemid, -1.0 AS critical_low, 4.0 AS critical_high),
      STRUCT('Arterial pH' AS lab_name, 50820 AS itemid, 7.2 AS critical_low, 7.6 AS critical_high),
      STRUCT('Creatinine' AS lab_name, 50912 AS itemid, -1.0 AS critical_low, 4.0 AS critical_high),
      STRUCT('WBC' AS lab_name, 51301 AS itemid, 2.0 AS critical_low, 30.0 AS critical_high),
      STRUCT('WBC' AS lab_name, 51300 AS itemid, 2.0 AS critical_low, 30.0 AS critical_high),
      STRUCT('Platelets' AS lab_name, 51265 AS itemid, 50.0 AS critical_low, 1000.0 AS critical_high)
    ])
  ),
  cohort_admissions AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON adm.subject_id = pat.subject_id
    WHERE
      pat.gender = 'F'
      AND ( (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age ) BETWEEN 52 AND 62
      AND adm.hadm_id IN (
        SELECT DISTINCT hadm_id
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          icd_code = '4275'
          OR STARTS_WITH(icd_code, 'I46')
      )
  ),
  cohort_lab_events AS (
    SELECT
      le.hadm_id,
      ld.lab_name,
      (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high) AS is_critical
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN cohort_admissions AS ca
      ON le.hadm_id = ca.hadm_id
    INNER JOIN lab_definitions AS ld
      ON le.itemid = ld.itemid
    WHERE
      le.charttime BETWEEN ca.admittime AND TIMESTAMP_ADD(ca.admittime, INTERVAL 48 HOUR)
      AND le.valuenum IS NOT NULL
  ),
  instability_scores AS (
    SELECT
      ca.hadm_id,
      ca.admittime,
      ca.dischtime,
      ca.hospital_expire_flag,
      COALESCE(crit_labs.instability_score, 0) AS instability_score
    FROM cohort_admissions AS ca
    LEFT JOIN (
      SELECT
        hadm_id,
        COUNT(DISTINCT lab_name) AS instability_score
      FROM cohort_lab_events
      WHERE is_critical = TRUE
      GROUP BY hadm_id
    ) AS crit_labs
    ON ca.hadm_id = crit_labs.hadm_id
  ),
  cohort_stats AS (
    SELECT
      'Post-Cardiac Arrest, F, 52-62' AS cohort_name,
      COUNT(DISTINCT hadm_id) AS cohort_size,
      AVG(hospital_expire_flag) * 100 AS mortality_rate_percent,
      AVG(TIMESTAMP_DIFF(dischtime, admittime, DAY)) AS avg_los_days,
      (SELECT COUNT(*) FROM cohort_lab_events WHERE is_critical = TRUE) AS total_critical_events,
      APPROX_QUANTILES(instability_score, 4) AS instability_score_quartiles
    FROM instability_scores
  ),
  general_pop_stats AS (
    SELECT
      'General Inpatient Population' AS population_name,
      COUNT(DISTINCT adm.hadm_id) AS population_size,
      COUNTIF(le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high) AS total_critical_events
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON adm.hadm_id = le.hadm_id
    INNER JOIN lab_definitions AS ld
      ON le.itemid = ld.itemid
    WHERE
      le.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 48 HOUR)
      AND le.valuenum IS NOT NULL
  )
SELECT
  cs.cohort_name,
  cs.cohort_size,
  ROUND(cs.mortality_rate_percent, 2) AS cohort_mortality_percent,
  ROUND(cs.avg_los_days, 1) AS cohort_avg_los_days,
  cs.instability_score_quartiles[OFFSET(1)] AS instability_score_q1,
  cs.instability_score_quartiles[OFFSET(2)] AS instability_score_median,
  cs.instability_score_quartiles[OFFSET(3)] AS instability_score_q3,
  (cs.instability_score_quartiles[OFFSET(3)] - cs.instability_score_quartiles[OFFSET(1)]) AS instability_score_interquartile_range,
  ROUND(SAFE_DIVIDE(cs.total_critical_events, cs.cohort_size), 2) AS cohort_critical_events_per_admission,
  ROUND(SAFE_DIVIDE(gps.total_critical_events, gps.population_size), 2) AS general_pop_critical_events_per_admission
FROM
  cohort_stats AS cs,
  general_pop_stats AS gps;
