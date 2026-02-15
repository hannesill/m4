WITH
lab_definitions AS (
  SELECT * FROM UNNEST([
    STRUCT('Sodium' AS lab_name, 50983 AS itemid, 120.0 AS critical_low, 160.0 AS critical_high),
    STRUCT('Potassium' AS lab_name, 50971 AS itemid, 2.5 AS critical_low, 6.5 AS critical_high),
    STRUCT('Creatinine' AS lab_name, 50912 AS itemid, NULL AS critical_low, 4.0 AS critical_high),
    STRUCT('Troponin T' AS lab_name, 51003 AS itemid, NULL AS critical_low, 0.1 AS critical_high),
    STRUCT('Glucose' AS lab_name, 50931 AS itemid, 50.0 AS critical_low, 400.0 AS critical_high),
    STRUCT('BUN' AS lab_name, 51006 AS itemid, NULL AS critical_low, 100.0 AS critical_high)
  ])
),
asthma_admissions AS (
  SELECT
    adm.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS los_days
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  WHERE
    pat.gender = 'M'
    AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 52 AND 62
    AND adm.hadm_id IN (
      SELECT DISTINCT hadm_id
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
      WHERE icd_code IN (
        '49301', '49311', '49321', '49391',
        'J4521', 'J4531', 'J4541', 'J4551', 'J45901'
      )
    )
),
age_matched_admissions AS (
  SELECT
    adm.subject_id,
    adm.hadm_id,
    adm.admittime
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  WHERE
    pat.gender = 'M'
    AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 52 AND 62
),
asthma_instability_scores AS (
  SELECT
    aa.hadm_id,
    aa.hospital_expire_flag,
    aa.los_days,
    COUNT(DISTINCT
      CASE
        WHEN (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high) THEN ld.itemid
        ELSE NULL
      END
    ) AS instability_score,
    COUNT(
      CASE
        WHEN (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high) THEN 1
        ELSE NULL
      END
    ) AS total_critical_events
  FROM asthma_admissions AS aa
  LEFT JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON aa.hadm_id = le.hadm_id
  INNER JOIN lab_definitions AS ld
    ON le.itemid = ld.itemid
  WHERE
    le.charttime BETWEEN aa.admittime AND DATETIME_ADD(aa.admittime, INTERVAL 72 HOUR)
    AND le.valuenum IS NOT NULL
  GROUP BY
    aa.hadm_id,
    aa.hospital_expire_flag,
    aa.los_days
),
asthma_p90_value AS (
  SELECT
    APPROX_QUANTILES(instability_score, 100)[OFFSET(90)] AS p90_instability_score
  FROM asthma_instability_scores
),
asthma_ranked_scores AS (
  SELECT
    ais.*,
    ap90.p90_instability_score,
    PERCENT_RANK() OVER(ORDER BY ais.instability_score) AS score_percentile_rank
  FROM asthma_instability_scores AS ais,
       asthma_p90_value AS ap90
),
top_tier_asthma_summary AS (
  SELECT
    MAX(p90_instability_score) AS p90_instability_score_for_asthma_cohort,
    COUNT(DISTINCT hadm_id) AS num_patients_in_top_tier,
    AVG(hospital_expire_flag) * 100 AS top_tier_mortality_rate_percent,
    AVG(los_days) AS top_tier_avg_los_days,
    SUM(total_critical_events) / COUNT(DISTINCT hadm_id) AS top_tier_avg_critical_events_per_patient
  FROM asthma_ranked_scores
  WHERE score_percentile_rank >= 0.9
),
age_matched_summary AS (
  SELECT
    SUM(
      CASE
        WHEN (le.valuenum < ld.critical_low OR le.valuenum > ld.critical_high) THEN 1
        ELSE 0
      END
    ) / COUNT(DISTINCT ama.hadm_id) AS comparison_avg_critical_events_per_patient
  FROM age_matched_admissions AS ama
  LEFT JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON ama.hadm_id = le.hadm_id
  INNER JOIN lab_definitions AS ld
    ON le.itemid = ld.itemid
  WHERE
    le.charttime BETWEEN ama.admittime AND DATETIME_ADD(ama.admittime, INTERVAL 72 HOUR)
    AND le.valuenum IS NOT NULL
)
SELECT
  asthma.p90_instability_score_for_asthma_cohort,
  asthma.top_tier_mortality_rate_percent,
  asthma.top_tier_avg_los_days,
  asthma.top_tier_avg_critical_events_per_patient,
  comp.comparison_avg_critical_events_per_patient
FROM top_tier_asthma_summary AS asthma,
     age_matched_summary AS comp;
