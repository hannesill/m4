WITH
  ich_cohort AS (
    SELECT
      adm.hadm_id,
      adm.subject_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      pat.anchor_age + DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
    WHERE
      pat.gender = 'M'
      AND (pat.anchor_age + DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 73 AND 83
      AND adm.hadm_id IN (
        SELECT DISTINCT
          dx.hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE
          STARTS_WITH(dx.icd_code, '430')
          OR STARTS_WITH(dx.icd_code, '431')
          OR STARTS_WITH(dx.icd_code, '432')
          OR STARTS_WITH(dx.icd_code, 'I60')
          OR STARTS_WITH(dx.icd_code, 'I61')
          OR STARTS_WITH(dx.icd_code, 'I62')
      )
  ),
  lab_panel AS (
    SELECT 'Sodium' AS lab_name, 50983 AS itemid, 135 AS lower_bound, 145 AS upper_bound UNION ALL
    SELECT 'Potassium', 50971, 3.5, 5.2 UNION ALL
    SELECT 'Creatinine', 50912, 0.6, 1.5 UNION ALL
    SELECT 'WBC', 51301, 4.0, 12.0 UNION ALL
    SELECT 'Platelet', 51265, 150, 450 UNION ALL
    SELECT 'INR', 51237, 0.8, 1.5 UNION ALL
    SELECT 'Lactate', 50813, 0.5, 2.0 UNION ALL
    SELECT 'Hemoglobin', 51222, 12.0, 17.5
  ),
  all_labs_first_48h AS (
    SELECT
      le.hadm_id,
      lp.lab_name,
      CASE
        WHEN le.valuenum < lp.lower_bound OR le.valuenum > lp.upper_bound THEN 1
        ELSE 0
      END AS is_abnormal,
      CASE
        WHEN ic.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS is_ich_cohort
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
      INNER JOIN lab_panel AS lp ON le.itemid = lp.itemid
      LEFT JOIN ich_cohort AS ic ON le.hadm_id = ic.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND le.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 48 HOUR)
  ),
  patient_level_abnormalities AS (
    SELECT
      hadm_id,
      lab_name,
      is_ich_cohort,
      MAX(is_abnormal) AS had_abnormal_value
    FROM
      all_labs_first_48h
    GROUP BY
      hadm_id,
      lab_name,
      is_ich_cohort
  ),
  instability_scores AS (
    SELECT
      hadm_id,
      SUM(had_abnormal_value) AS instability_score
    FROM
      patient_level_abnormalities
    WHERE
      is_ich_cohort = 1
    GROUP BY
      hadm_id
  ),
  instability_quartiles AS (
    SELECT
      sc.hadm_id,
      ic.hospital_expire_flag,
      DATETIME_DIFF(ic.dischtime, ic.admittime, DAY) AS los_days,
      sc.instability_score,
      NTILE(4) OVER (
        ORDER BY
          sc.instability_score
      ) AS instability_quartile
    FROM
      instability_scores AS sc
      INNER JOIN ich_cohort AS ic ON sc.hadm_id = ic.hadm_id
  ),
  outcomes_by_quartile AS (
    SELECT
      instability_quartile,
      COUNT(hadm_id) AS patient_count,
      AVG(los_days) AS avg_los_days,
      AVG(CAST(hospital_expire_flag AS INT64)) AS mortality_rate
    FROM
      instability_quartiles
    GROUP BY
      instability_quartile
  ),
  critical_rate_comparison AS (
    SELECT
      lab_name,
      SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN is_ich_cohort = 1 AND had_abnormal_value = 1 THEN hadm_id END),
        COUNT(DISTINCT CASE WHEN is_ich_cohort = 1 THEN hadm_id END)
      ) AS ich_cohort_critical_rate,
      SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN had_abnormal_value = 1 THEN hadm_id END),
        COUNT(DISTINCT hadm_id)
      ) AS general_population_critical_rate
    FROM
      patient_level_abnormalities
    GROUP BY
      lab_name
  )
SELECT
  'Quartile Outcomes' AS report_type,
  CONCAT('Quartile ', CAST(instability_quartile AS STRING)) AS stratum,
  'patient_count' AS metric_1_name,
  CAST(patient_count AS STRING) AS metric_1_value,
  'avg_los_days' AS metric_2_name,
  CAST(ROUND(avg_los_days, 2) AS STRING) AS metric_2_value,
  'mortality_rate' AS metric_3_name,
  CAST(ROUND(mortality_rate, 3) AS STRING) AS metric_3_value
FROM
  outcomes_by_quartile
UNION ALL
SELECT
  'Critical Rate Comparison' AS report_type,
  lab_name AS stratum,
  'ich_cohort_critical_rate' AS metric_1_name,
  CAST(ROUND(ich_cohort_critical_rate, 3) AS STRING) AS metric_1_value,
  'general_population_critical_rate' AS metric_2_name,
  CAST(ROUND(general_population_critical_rate, 3) AS STRING) AS metric_2_value,
  NULL AS metric_3_name,
  NULL AS metric_3_value
FROM
  critical_rate_comparison
ORDER BY
  report_type,
  stratum;
