WITH
  lab_definitions AS (
    SELECT 50983 AS itemid, 'Sodium' AS label, 120 AS critical_low, 160 AS critical_high UNION ALL
    SELECT 50824 AS itemid, 'Sodium' AS label, 120 AS critical_low, 160 AS critical_high UNION ALL
    SELECT 50971 AS itemid, 'Potassium' AS label, 2.5 AS critical_low, 6.5 AS critical_high UNION ALL
    SELECT 50822 AS itemid, 'Potassium' AS label, 2.5 AS critical_low, 6.5 AS critical_high UNION ALL
    SELECT 50912 AS itemid, 'Creatinine' AS label, NULL AS critical_low, 4.0 AS critical_high UNION ALL
    SELECT 50813 AS itemid, 'Creatinine' AS label, NULL AS critical_low, 4.0 AS critical_high UNION ALL
    SELECT 50882 AS itemid, 'Bicarbonate' AS label, 10 AS critical_low, 40 AS critical_high UNION ALL
    SELECT 50803 AS itemid, 'Bicarbonate' AS label, 10 AS critical_low, 40 AS critical_high UNION ALL
    SELECT 51301 AS itemid, 'WBC' AS label, 2.0 AS critical_low, 30.0 AS critical_high UNION ALL
    SELECT 51300 AS itemid, 'WBC' AS label, 2.0 AS critical_low, 30.0 AS critical_high UNION ALL
    SELECT 51265 AS itemid, 'Platelets' AS label, 20 AS critical_low, NULL AS critical_high UNION ALL
    SELECT 51222 AS itemid, 'Hemoglobin' AS label, 7 AS critical_low, NULL AS critical_high UNION ALL
    SELECT 50811 AS itemid, 'Hemoglobin' AS label, 7 AS critical_low, NULL AS critical_high
  ),
  base_female_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age) BETWEEN 48 AND 58
  ),
  hemorrhagic_stroke_cohort AS (
    SELECT
      bfc.subject_id,
      bfc.hadm_id,
      bfc.admittime,
      bfc.dischtime,
      bfc.hospital_expire_flag
    FROM base_female_cohort AS bfc
    WHERE EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      WHERE dx.hadm_id = bfc.hadm_id
      AND (
        (dx.icd_version = 9 AND (dx.icd_code LIKE '430%' OR dx.icd_code LIKE '431%' OR dx.icd_code LIKE '432%'))
        OR
        (dx.icd_version = 10 AND (dx.icd_code LIKE 'I60%' OR dx.icd_code LIKE 'I61%' OR dx.icd_code LIKE 'I62%'))
      )
    )
  ),
  comparison_cohort AS (
    SELECT
      bfc.subject_id,
      bfc.hadm_id,
      bfc.admittime
    FROM base_female_cohort AS bfc
    WHERE bfc.hadm_id NOT IN (SELECT hadm_id FROM hemorrhagic_stroke_cohort)
  ),
  all_relevant_labevents AS (
    SELECT
      le.hadm_id,
      ld.label,
      CASE
        WHEN le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high THEN 1
        ELSE 0
      END AS is_critical
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN lab_definitions AS ld
      ON le.itemid = ld.itemid
    INNER JOIN (
      SELECT hadm_id, admittime FROM hemorrhagic_stroke_cohort
      UNION ALL
      SELECT hadm_id, admittime FROM comparison_cohort
    ) AS all_cohorts
      ON le.hadm_id = all_cohorts.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND le.charttime BETWEEN all_cohorts.admittime AND TIMESTAMP_ADD(all_cohorts.admittime, INTERVAL 72 HOUR)
  ),
  stroke_instability_scores AS (
    SELECT
      hsc.hadm_id,
      hsc.hospital_expire_flag,
      DATETIME_DIFF(hsc.dischtime, hsc.admittime, DAY) AS los_days,
      COUNT(DISTINCT arl.label) AS instability_score
    FROM hemorrhagic_stroke_cohort AS hsc
    LEFT JOIN all_relevant_labevents AS arl
      ON hsc.hadm_id = arl.hadm_id AND arl.is_critical = 1
    GROUP BY
      hsc.hadm_id, hsc.hospital_expire_flag, hsc.dischtime, hsc.admittime
  ),
  stroke_cohort_tiered AS (
    SELECT
      hadm_id,
      instability_score,
      los_days,
      hospital_expire_flag,
      PERCENTILE_CONT(instability_score, 0.9) OVER() AS p90_instability_score
    FROM stroke_instability_scores
  ),
  top_tier_stroke_stats AS (
    SELECT
      DISTINCT p90_instability_score,
      COUNT(hadm_id) AS top_tier_patient_count,
      AVG(los_days) AS avg_los_top_tier,
      AVG(hospital_expire_flag) * 100 AS mortality_rate_top_tier_percent
    FROM stroke_cohort_tiered
    WHERE instability_score >= p90_instability_score AND p90_instability_score > 0
    GROUP BY p90_instability_score
  ),
  critical_lab_rates AS (
    SELECT
      group_name,
      COUNT(DISTINCT hadm_id) AS total_patients,
      SUM(is_critical) AS total_critical_events,
      SAFE_DIVIDE(SUM(is_critical), COUNT(DISTINCT hadm_id)) AS avg_critical_events_per_patient
    FROM (
      SELECT
        arl.hadm_id,
        arl.is_critical,
        'Top_Tier_Stroke_Patients' AS group_name
      FROM all_relevant_labevents AS arl
      WHERE arl.hadm_id IN (SELECT hadm_id FROM stroke_cohort_tiered WHERE instability_score >= p90_instability_score AND p90_instability_score > 0)
      UNION ALL
      SELECT
        arl.hadm_id,
        arl.is_critical,
        'Age_Matched_Comparison_Cohort' AS group_name
      FROM all_relevant_labevents AS arl
      WHERE arl.hadm_id IN (SELECT hadm_id FROM comparison_cohort)
    ) AS combined_groups
    GROUP BY group_name
  )
SELECT
  t.p90_instability_score,
  t.top_tier_patient_count,
  t.mortality_rate_top_tier_percent,
  t.avg_los_top_tier,
  (SELECT avg_critical_events_per_patient FROM critical_lab_rates WHERE group_name = 'Top_Tier_Stroke_Patients') AS top_tier_avg_critical_events,
  (SELECT avg_critical_events_per_patient FROM critical_lab_rates WHERE group_name = 'Age_Matched_Comparison_Cohort') AS comparison_cohort_avg_critical_events
FROM top_tier_stroke_stats AS t;
