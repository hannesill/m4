WITH
  lab_definitions AS (
    SELECT 50983 AS itemid, 'Sodium' AS lab_name, 120 AS critical_low, 160 AS critical_high UNION ALL
    SELECT 50971, 'Potassium', 2.5, 6.5 UNION ALL
    SELECT 50912, 'Creatinine', NULL, 4.0 UNION ALL
    SELECT 51301, 'WBC', 2, 50 UNION ALL
    SELECT 51265, 'Platelet', 20, NULL UNION ALL
    SELECT 50813, 'Lactate', NULL, 4.0 UNION ALL
    SELECT 50820, 'pH', 7.2, 7.6 UNION ALL
    SELECT 50882, 'Bicarbonate', 10, 40
  ),
  sepsis_cohort_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) BETWEEN 43 AND 53
      AND a.hadm_id IN (
        SELECT DISTINCT hadm_id
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          STARTS_WITH(icd_code, 'R652')
          OR STARTS_WITH(icd_code, 'A41')
          OR icd_code IN ('99591', '99592', '78552')
      )
  ),
  all_critical_labs_72h AS (
    SELECT
      le.hadm_id,
      ld.lab_name
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON le.hadm_id = a.hadm_id
    INNER JOIN
      lab_definitions AS ld ON le.itemid = ld.itemid
    WHERE
      le.valuenum IS NOT NULL
      AND le.charttime BETWEEN a.admittime AND TIMESTAMP_ADD(a.admittime, INTERVAL 72 HOUR)
      AND (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high)
  ),
  sepsis_cohort_instability AS (
    SELECT
      s.hadm_id,
      s.subject_id,
      DATETIME_DIFF(s.dischtime, s.admittime, HOUR) / 24.0 AS los_days,
      s.hospital_expire_flag AS mortality_flag,
      COUNT(acl.lab_name) AS instability_score
    FROM
      sepsis_cohort_admissions AS s
    LEFT JOIN
      all_critical_labs_72h AS acl ON s.hadm_id = acl.hadm_id
    GROUP BY
      s.hadm_id,
      s.subject_id,
      s.dischtime,
      s.admittime,
      s.hospital_expire_flag
  ),
  sepsis_cohort_summary AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(25)] AS sepsis_cohort_p25_instability_score,
      AVG(instability_score) AS sepsis_cohort_avg_critical_events_per_admission,
      AVG(los_days) AS sepsis_cohort_avg_los_days,
      AVG(CAST(mortality_flag AS FLOAT64)) AS sepsis_cohort_mortality_rate
    FROM
      sepsis_cohort_instability
  ),
  general_cohort_summary AS (
    SELECT
      SAFE_DIVIDE(
        CAST((SELECT COUNT(*) FROM all_critical_labs_72h) AS FLOAT64),
        CAST((SELECT COUNT(DISTINCT hadm_id) FROM `physionet-data.mimiciv_3_1_hosp.admissions`) AS FLOAT64)
      ) AS general_cohort_avg_critical_events_per_admission
  )
SELECT
  s_summary.sepsis_cohort_p25_instability_score,
  s_summary.sepsis_cohort_avg_critical_events_per_admission,
  g_summary.general_cohort_avg_critical_events_per_admission,
  s_summary.sepsis_cohort_avg_los_days,
  s_summary.sepsis_cohort_mortality_rate
FROM
  sepsis_cohort_summary AS s_summary,
  general_cohort_summary AS g_summary;
