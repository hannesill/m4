WITH
  target_cohort_admissions AS (
    SELECT DISTINCT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON adm.subject_id = p.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON adm.hadm_id = dx.hadm_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM adm.admittime) - p.anchor_year + p.anchor_age) BETWEEN 78 AND 88
      AND (
        (dx.icd_version = 9 AND (dx.icd_code LIKE '433.%1' OR dx.icd_code LIKE '434.%1'))
        OR
        (dx.icd_version = 10 AND STARTS_WITH(dx.icd_code, 'I63'))
      )
  ),
  critical_lab_definitions AS (
    SELECT 50971 AS itemid, 'Potassium' AS label, 2.5 AS lower_bound, 6.5 AS upper_bound UNION ALL
    SELECT 50822 AS itemid, 'Potassium', 2.5, 6.5 UNION ALL
    SELECT 50983 AS itemid, 'Sodium' AS label, 120 AS lower_bound, 160 AS upper_bound UNION ALL
    SELECT 50824 AS itemid, 'Sodium', 120, 160 UNION ALL
    SELECT 50912 AS itemid, 'Creatinine' AS label, NULL AS lower_bound, 4.0 AS upper_bound UNION ALL
    SELECT 50813 AS itemid, 'Lactate' AS label, NULL AS lower_bound, 4.0 AS upper_bound UNION ALL
    SELECT 51301 AS itemid, 'WBC' AS label, 2.0 AS lower_bound, 30.0 AS upper_bound UNION ALL
    SELECT 51300 AS itemid, 'WBC', 2.0, 30.0 UNION ALL
    SELECT 51265 AS itemid, 'Platelets' AS label, 20.0 AS lower_bound, NULL AS upper_bound
  ),
  cohort_critical_events_72h AS (
    SELECT
      le.hadm_id,
      le.itemid
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      target_cohort_admissions AS tca
      ON le.hadm_id = tca.hadm_id
    INNER JOIN
      critical_lab_definitions AS cld
      ON le.itemid = cld.itemid
    WHERE
      le.valuenum IS NOT NULL
      AND le.charttime BETWEEN tca.admittime AND TIMESTAMP_ADD(tca.admittime, INTERVAL 72 HOUR)
      AND (le.valuenum < cld.lower_bound OR le.valuenum > cld.upper_bound)
  ),
  cohort_instability_scores AS (
    SELECT
      tca.hadm_id,
      tca.subject_id,
      tca.admittime,
      tca.dischtime,
      tca.hospital_expire_flag,
      COUNT(cce.itemid) AS instability_score
    FROM
      target_cohort_admissions AS tca
    LEFT JOIN
      cohort_critical_events_72h AS cce
      ON tca.hadm_id = cce.hadm_id
    GROUP BY
      tca.hadm_id, tca.subject_id, tca.admittime, tca.dischtime, tca.hospital_expire_flag
  )
SELECT
  'Female, 78-88, Acute Ischemic Stroke' AS cohort_description,
  COUNT(hadm_id) AS number_of_patients_in_cohort,
  MIN(instability_score) AS min_instability_score_cohort,
  APPROX_QUANTILES(instability_score, 4) [OFFSET(1)] AS p25_instability_score_cohort,
  APPROX_QUANTILES(instability_score, 4) [OFFSET(2)] AS median_instability_score_cohort,
  APPROX_QUANTILES(instability_score, 4) [OFFSET(3)] AS p75_instability_score_cohort,
  MAX(instability_score) AS max_instability_score_cohort,
  AVG(instability_score) AS avg_instability_score_cohort,
  (
    SELECT
      SAFE_DIVIDE(
        COUNT(*),
        (SELECT COUNT(DISTINCT hadm_id) FROM `physionet-data.mimiciv_3_1_hosp.admissions`)
      )
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` le
    JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm ON le.hadm_id = adm.hadm_id
    JOIN critical_lab_definitions cld ON le.itemid = cld.itemid
    WHERE le.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 72 HOUR)
      AND (le.valuenum < cld.lower_bound OR le.valuenum > cld.upper_bound)
  ) AS avg_critical_events_per_general_admission,
  AVG(TIMESTAMP_DIFF(dischtime, admittime, HOUR) / 24.0) AS avg_length_of_stay_days_cohort,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate_cohort
FROM
  cohort_instability_scores;
