WITH
  asthma_admissions AS (
    SELECT DISTINCT
      hadm_id,
      subject_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9 AND icd_code LIKE '493%'
      )
      OR (
        icd_version = 10 AND icd_code LIKE 'J45%'
      )
  ),
  target_cohort AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON adm.subject_id = p.subject_id
      INNER JOIN asthma_admissions AS aa ON adm.hadm_id = aa.hadm_id
    WHERE
      p.gender = 'F'
      AND (
        (EXTRACT(YEAR FROM adm.admittime) - p.anchor_year) + p.anchor_age BETWEEN 55 AND 65
      )
  ),
  critical_labs_definition AS (
    SELECT 50983 AS itemid, 'Sodium' AS label,       120 AS critical_low, 160 AS critical_high UNION ALL
    SELECT 50971 AS itemid, 'Potassium' AS label,    2.5 AS critical_low, 6.5 AS critical_high UNION ALL
    SELECT 50912 AS itemid, 'Creatinine' AS label,   NULL AS critical_low, 4.0 AS critical_high UNION ALL
    SELECT 50882 AS itemid, 'Bicarbonate' AS label,  10 AS critical_low, 40 AS critical_high UNION ALL
    SELECT 51301 AS itemid, 'WBC' AS label,          2.0 AS critical_low, 30.0 AS critical_high UNION ALL
    SELECT 51222 AS itemid, 'Hemoglobin' AS label,   7.0 AS critical_low, NULL AS critical_high UNION ALL
    SELECT 51265 AS itemid, 'Platelet Count' AS label, 20.0 AS critical_low, NULL AS critical_high UNION ALL
    SELECT 50931 AS itemid, 'Glucose' AS label,      50 AS critical_low, 400 AS critical_high
  ),
  all_labevents_first_48h AS (
    SELECT
      le.hadm_id,
      le.itemid,
      le.valuenum
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND le.itemid IN (
        SELECT itemid FROM critical_labs_definition
      )
      AND TIMESTAMP_DIFF(le.charttime, adm.admittime, HOUR) BETWEEN 0 AND 48
  ),
  critical_events AS (
    SELECT
      le.hadm_id,
      le.itemid
    FROM
      all_labevents_first_48h AS le
      INNER JOIN critical_labs_definition AS def ON le.itemid = def.itemid
    WHERE
      (le.valuenum < def.critical_low) OR (le.valuenum > def.critical_high)
  ),
  instability_scores AS (
    SELECT
      tc.subject_id,
      tc.hadm_id,
      tc.admittime,
      tc.dischtime,
      tc.hospital_expire_flag,
      COUNT(ce.itemid) AS instability_score
    FROM
      target_cohort AS tc
      LEFT JOIN critical_events AS ce ON tc.hadm_id = ce.hadm_id
    GROUP BY
      tc.subject_id,
      tc.hadm_id,
      tc.admittime,
      tc.dischtime,
      tc.hospital_expire_flag
  ),
  cohort_percentiles AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(95)] AS p95_instability_score
    FROM
      instability_scores
  ),
  top_tier_cohort AS (
    SELECT
      iss.hadm_id,
      iss.hospital_expire_flag,
      TIMESTAMP_DIFF(iss.dischtime, iss.admittime, HOUR) / 24.0 AS los
    FROM
      instability_scores AS iss,
      cohort_percentiles AS cp
    WHERE
      iss.instability_score >= cp.p95_instability_score
  ),
  top_tier_outcomes AS (
    SELECT
      COUNT(hadm_id) AS num_top_tier_patients,
      AVG(los) AS avg_los_top_tier,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate_top_tier
    FROM
      top_tier_cohort
  ),
  critical_rate_calculation AS (
    SELECT
      SAFE_DIVIDE(
        (
          SELECT COUNT(*) FROM critical_events WHERE hadm_id IN (SELECT hadm_id FROM top_tier_cohort)
        ),
        (
          SELECT COUNT(*) FROM all_labevents_first_48h WHERE hadm_id IN (SELECT hadm_id FROM top_tier_cohort)
        )
      ) AS critical_lab_rate_top_tier,
      SAFE_DIVIDE(
        (
          SELECT COUNT(*) FROM critical_events
        ),
        (
          SELECT COUNT(*) FROM all_labevents_first_48h
        )
      ) AS critical_lab_rate_general_inpatients
  )
SELECT
  cp.p95_instability_score,
  tto.num_top_tier_patients,
  tto.avg_los_top_tier,
  tto.mortality_rate_top_tier,
  crc.critical_lab_rate_top_tier,
  crc.critical_lab_rate_general_inpatients
FROM
  cohort_percentiles AS cp,
  top_tier_outcomes AS tto,
  critical_rate_calculation AS crc;
