WITH
septic_shock_stays AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code IN ('R6521', '78552')
),
cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN septic_shock_stays AS sss
    ON a.hadm_id = sss.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 89 AND 99
),
lab_events_cohort AS (
  SELECT
    c.hadm_id,
    le.itemid,
    le.valuenum
  FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN cohort AS c
    ON le.hadm_id = c.hadm_id
  WHERE
    le.itemid IN (50912, 51003, 50983, 50971, 50931, 51006)
    AND le.charttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 48 HOUR)
    AND le.valuenum IS NOT NULL
),
lab_abnormalities_cohort AS (
  SELECT
    hadm_id,
    itemid,
    CASE
      WHEN itemid = 50912 AND valuenum > 1.2 THEN 1
      WHEN itemid = 51003 AND valuenum > 0.01 THEN 1
      WHEN itemid = 50983 AND (valuenum < 135 OR valuenum > 145) THEN 1
      WHEN itemid = 50971 AND (valuenum < 3.5 OR valuenum > 5.2) THEN 1
      WHEN itemid = 50931 AND (valuenum < 70 OR valuenum > 180) THEN 1
      WHEN itemid = 51006 AND valuenum > 20 THEN 1
      ELSE 0
    END AS is_abnormal
  FROM lab_events_cohort
),
instability_scores AS (
  SELECT
    hadm_id,
    (COUNT(DISTINCT itemid) / 6.0) * 100 AS instability_score
  FROM lab_abnormalities_cohort
  WHERE is_abnormal = 1
  GROUP BY hadm_id
),
cohort_with_scores_and_outcomes AS (
  SELECT
    c.hadm_id,
    c.hospital_expire_flag,
    DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
    COALESCE(iss.instability_score, 0) AS instability_score
  FROM cohort AS c
  LEFT JOIN instability_scores AS iss
    ON c.hadm_id = iss.hadm_id
),
lab_events_general AS (
  SELECT
    le.itemid,
    le.valuenum
  FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON le.hadm_id = a.hadm_id
  WHERE
    le.itemid IN (50912, 51003, 50983, 50971, 50931, 51006)
    AND le.charttime BETWEEN a.admittime AND DATETIME_ADD(a.admittime, INTERVAL 48 HOUR)
    AND le.valuenum IS NOT NULL
),
lab_abnormalities_general AS (
  SELECT
    CASE
      WHEN itemid = 50912 AND valuenum > 1.2 THEN 1
      WHEN itemid = 51003 AND valuenum > 0.01 THEN 1
      WHEN itemid = 50983 AND (valuenum < 135 OR valuenum > 145) THEN 1
      WHEN itemid = 50971 AND (valuenum < 3.5 OR valuenum > 5.2) THEN 1
      WHEN itemid = 50931 AND (valuenum < 70 OR valuenum > 180) THEN 1
      WHEN itemid = 51006 AND valuenum > 20 THEN 1
      ELSE 0
    END AS is_abnormal
  FROM lab_events_general
),
summary_metrics AS (
  SELECT
    (SELECT
      STRUCT(
        quantiles[OFFSET(1)] AS q1_instability_score,
        quantiles[OFFSET(2)] AS median_instability_score,
        quantiles[OFFSET(3)] AS q3_instability_score,
        quantiles[OFFSET(3)] - quantiles[OFFSET(1)] AS iqr_instability_score
      )
     FROM (SELECT APPROX_QUANTILES(instability_score, 4) AS quantiles FROM cohort_with_scores_and_outcomes)
    ) AS cohort_scores,
    (SELECT STRUCT(AVG(los_days) AS avg_los_days, AVG(hospital_expire_flag) AS mortality_rate)
     FROM cohort_with_scores_and_outcomes
    ) AS cohort_outcomes,
    (SELECT STRUCT(SAFE_DIVIDE(COUNTIF(is_abnormal = 1), COUNT(*)) AS cohort_abnormal_lab_freq)
     FROM lab_abnormalities_cohort
    ) AS cohort_freq,
    (SELECT STRUCT(SAFE_DIVIDE(COUNTIF(is_abnormal = 1), COUNT(*)) AS general_pop_abnormal_lab_freq)
     FROM lab_abnormalities_general
    ) AS general_freq
)
SELECT
  sm.cohort_scores.q1_instability_score,
  sm.cohort_scores.median_instability_score,
  sm.cohort_scores.q3_instability_score,
  sm.cohort_scores.iqr_instability_score,
  sm.cohort_outcomes.avg_los_days,
  sm.cohort_outcomes.mortality_rate,
  sm.cohort_freq.cohort_abnormal_lab_freq,
  sm.general_freq.general_pop_abnormal_lab_freq
FROM summary_metrics AS sm;
