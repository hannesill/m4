WITH
lab_definitions AS (
  SELECT 50971 AS itemid, 'Potassium' AS lab_name, 2.5 AS critical_low, 6.5 AS critical_high UNION ALL
  SELECT 50824 AS itemid, 'Sodium' AS lab_name, 120 AS critical_low, 160 AS critical_high UNION ALL
  SELECT 50912 AS itemid, 'Creatinine' AS lab_name, NULL AS critical_low, 4.0 AS critical_high UNION ALL
  SELECT 50813 AS itemid, 'Lactate' AS lab_name, NULL AS critical_low, 4.0 AS critical_high UNION ALL
  SELECT 51301 AS itemid, 'WBC' AS lab_name, 2.0 AS critical_low, 30.0 AS critical_high UNION ALL
  SELECT 51265 AS itemid, 'Platelet Count' AS lab_name, 20.0 AS critical_low, NULL AS critical_high UNION ALL
  SELECT 50820 AS itemid, 'pH' AS lab_name, 7.20 AS critical_low, 7.60 AS critical_high
),
hf_cohort AS (
  SELECT DISTINCT
    adm.hadm_id,
    adm.subject_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON adm.hadm_id = dx.hadm_id
  WHERE
    pat.gender = 'M'
    AND (pat.anchor_age + DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 37 AND 47
    AND (dx.icd_code LIKE 'I50%' OR dx.icd_code LIKE '428%')
),
cohort_critical_events AS (
  SELECT
    hf.hadm_id,
    ld.lab_name
  FROM hf_cohort AS hf
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON hf.hadm_id = le.hadm_id
  INNER JOIN lab_definitions AS ld
    ON le.itemid = ld.itemid
  WHERE
    le.valuenum IS NOT NULL
    AND DATETIME_DIFF(le.charttime, hf.admittime, HOUR) BETWEEN 0 AND 72
    AND (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high)
),
cohort_instability_scores AS (
  SELECT
    hf.hadm_id,
    COALESCE(crit.instability_score, 0) AS instability_score
  FROM hf_cohort AS hf
  LEFT JOIN (
    SELECT
      hadm_id,
      COUNT(DISTINCT lab_name) AS instability_score
    FROM cohort_critical_events
    GROUP BY hadm_id
  ) AS crit
  ON hf.hadm_id = crit.hadm_id
),
general_pop_critical_events AS (
  SELECT
    adm.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON adm.hadm_id = le.hadm_id
  INNER JOIN lab_definitions AS ld
    ON le.itemid = ld.itemid
  WHERE
    le.valuenum IS NOT NULL
    AND DATETIME_DIFF(le.charttime, adm.admittime, HOUR) BETWEEN 0 AND 72
    AND (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high)
)
SELECT
  'Male inpatients aged 37-47 with Heart Failure' AS target_cohort_description,
  (SELECT COUNT(DISTINCT hadm_id) FROM hf_cohort) AS cohort_size,
  (SELECT MAX(instability_score) FROM cohort_instability_scores) AS max_instability_score_in_cohort,
  (SELECT APPROX_QUANTILES(instability_score, 100) FROM cohort_instability_scores)[OFFSET(25)] AS p25_instability_score,
  (SELECT APPROX_QUANTILES(instability_score, 100) FROM cohort_instability_scores)[OFFSET(50)] AS p50_instability_score,
  (SELECT APPROX_QUANTILES(instability_score, 100) FROM cohort_instability_scores)[OFFSET(75)] AS p75_instability_score,
  (SELECT APPROX_QUANTILES(instability_score, 100) FROM cohort_instability_scores)[OFFSET(95)] AS p95_instability_score,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM cohort_critical_events),
    (SELECT COUNT(DISTINCT hadm_id) FROM hf_cohort)
  ) AS avg_critical_events_per_admission_cohort,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM general_pop_critical_events),
    (SELECT COUNT(DISTINCT hadm_id) FROM `physionet-data.mimiciv_3_1_hosp.admissions`)
  ) AS avg_critical_events_per_admission_general_pop,
  (SELECT AVG(DATETIME_DIFF(dischtime, admittime, DAY)) FROM hf_cohort) AS avg_los_days_cohort,
  (SELECT AVG(CAST(hospital_expire_flag AS FLOAT64)) FROM hf_cohort) AS mortality_rate_cohort;
