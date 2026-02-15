WITH
  lab_definitions AS (
    SELECT 51221 AS itemid, 'Hemoglobin' AS lab_name, 12.0 AS normal_low, 16.0 AS normal_high, 7.0 AS critical_low, 999 AS critical_high UNION ALL
    SELECT 51265, 'Platelets', 150.0, 450.0, 50.0, 9999 UNION ALL
    SELECT 50971, 'Potassium', 3.5, 5.2, 2.5, 6.5 UNION ALL
    SELECT 50983, 'Sodium', 135.0, 145.0, 120.0, 160.0 UNION ALL
    SELECT 50912, 'Creatinine', 0.6, 1.2, 0, 4.0 UNION ALL
    SELECT 50882, 'Bicarbonate', 22.0, 28.0, 10.0, 999 UNION ALL
    SELECT 50813, 'Lactate', 0.5, 1.0, 0, 4.0 UNION ALL
    SELECT 51301, 'WBC', 4.5, 11.0, 2.0, 30.0
  ),
  target_cohort_admissions AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
    WHERE
      pat.gender = 'F'
      AND (
        (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age
      ) BETWEEN 65 AND 75
      AND adm.hadm_id IN (
        SELECT DISTINCT hadm_id
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          icd_code IN (
            '5781',
            '5693',
            'K921',
            'K922',
            'K625'
          )
      )
  ),
  lab_deviations AS (
    SELECT
      le.hadm_id,
      POW(
        CASE
          WHEN le.valuenum < def.normal_low THEN (le.valuenum - def.normal_low) / (def.normal_high - def.normal_low)
          WHEN le.valuenum > def.normal_high THEN (le.valuenum - def.normal_high) / (def.normal_high - def.normal_low)
          ELSE 0
        END,
        2
      ) AS normalized_deviation_squared,
      CASE
        WHEN le.valuenum < def.critical_low OR le.valuenum > def.critical_high THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
      INNER JOIN lab_definitions AS def ON le.itemid = def.itemid
    WHERE
      le.valuenum IS NOT NULL
      AND TIMESTAMP_DIFF(le.charttime, adm.admittime, HOUR) BETWEEN 0 AND 72
  ),
  admission_scores AS (
    SELECT
      hadm_id,
      SUM(normalized_deviation_squared) AS instability_score,
      SUM(is_critical) AS critical_event_count
    FROM
      lab_deviations
    GROUP BY
      hadm_id
  ),
  target_cohort_results AS (
    SELECT
      APPROX_QUANTILES(scores.instability_score, 100)[OFFSET(25)] AS p25_instability_score_target_cohort,
      AVG(TIMESTAMP_DIFF(cohort.dischtime, cohort.admittime, HOUR) / 24.0) AS avg_los_days_target_cohort,
      AVG(CAST(cohort.hospital_expire_flag AS FLOAT64)) AS mortality_rate_target_cohort,
      SUM(scores.critical_event_count) / COUNT(DISTINCT cohort.hadm_id) AS avg_critical_events_per_admission_target
    FROM
      target_cohort_admissions AS cohort
      INNER JOIN admission_scores AS scores ON cohort.hadm_id = scores.hadm_id
  ),
  general_cohort_results AS (
    SELECT
      SUM(critical_event_count) / COUNT(DISTINCT hadm_id) AS avg_critical_events_per_admission_general
    FROM
      admission_scores
  )
SELECT
  target.p25_instability_score_target_cohort,
  target.avg_critical_events_per_admission_target,
  general.avg_critical_events_per_admission_general,
  target.avg_los_days_target_cohort,
  target.mortality_rate_target_cohort
FROM
  target_cohort_results AS target,
  general_cohort_results AS general;
