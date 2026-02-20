WITH
acs_cohort AS (
  SELECT
    pat.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS pat
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    ON pat.subject_id = adm.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON adm.hadm_id = dx.hadm_id
  WHERE
    pat.gender = 'F'
    AND (
      (dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code = '4111'))
      OR (dx.icd_version = 10 AND (dx.icd_code LIKE 'I200%' OR dx.icd_code LIKE 'I21%' OR dx.icd_code LIKE 'I22%'))
    )
  GROUP BY 1, 2, 3, 4, 5, 6
  HAVING age_at_admission BETWEEN 40 AND 50
),
critical_lab_definitions AS (
  SELECT 50971 AS itemid, 'Potassium' AS lab_name, 2.5 AS critical_low, 6.0 AS critical_high UNION ALL
  SELECT 50983, 'Sodium', 120, 160 UNION ALL
  SELECT 50912, 'Creatinine', NULL, 4.0 UNION ALL
  SELECT 51003, 'Troponin T', NULL, 1.0 UNION ALL
  SELECT 50931, 'Glucose', 60, 400 UNION ALL
  SELECT 51006, 'BUN', NULL, 100
),
cohort_labs_first_48h AS (
  SELECT
    le.hadm_id,
    le.itemid,
    le.valuenum
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN
    acs_cohort AS cohort
    ON le.hadm_id = cohort.hadm_id
  WHERE
    le.valuenum IS NOT NULL
    AND le.charttime BETWEEN cohort.admittime AND DATETIME_ADD(cohort.admittime, INTERVAL 48 HOUR)
    AND le.itemid IN (SELECT itemid FROM critical_lab_definitions)
),
cohort_critical_events AS (
  SELECT
    labs.hadm_id,
    labs.itemid
  FROM
    cohort_labs_first_48h AS labs
  INNER JOIN
    critical_lab_definitions AS def
    ON labs.itemid = def.itemid
  WHERE
    (def.critical_low IS NOT NULL AND labs.valuenum < def.critical_low)
    OR (def.critical_high IS NOT NULL AND labs.valuenum > def.critical_high)
),
cohort_instability_scores AS (
  SELECT
    cohort.hadm_id,
    cohort.hospital_expire_flag,
    cohort.admittime,
    cohort.dischtime,
    COUNT(crit.itemid) AS instability_score
  FROM
    acs_cohort AS cohort
  LEFT JOIN
    cohort_critical_events AS crit
    ON cohort.hadm_id = crit.hadm_id
  GROUP BY
    1, 2, 3, 4
),
scores_with_percentile AS (
  SELECT
    s.*,
    PERCENTILE_CONT(instability_score, 0.9) OVER() AS p90_instability_score
  FROM
    cohort_instability_scores AS s
),
top_tier_outcomes AS (
  SELECT
    ANY_VALUE(p90_instability_score) AS p90_instability_score,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS top_tier_mortality_rate,
    AVG(DATETIME_DIFF(dischtime, admittime, DAY)) AS top_tier_avg_los_days
  FROM
    scores_with_percentile
  WHERE
    instability_score >= p90_instability_score
),
top_tier_rate AS (
  SELECT
    SAFE_DIVIDE(
      (SELECT COUNT(*) FROM cohort_critical_events WHERE hadm_id IN (SELECT hadm_id FROM scores_with_percentile WHERE instability_score >= p90_instability_score)),
      (SELECT COUNT(*) FROM cohort_labs_first_48h WHERE hadm_id IN (SELECT hadm_id FROM scores_with_percentile WHERE instability_score >= p90_instability_score))
    ) AS top_tier_critical_lab_rate
),
general_population_rate AS (
  WITH
  general_labs AS (
    SELECT
      le.itemid,
      le.valuenum
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
    WHERE le.valuenum IS NOT NULL
      AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 48 HOUR)
      AND le.itemid IN (SELECT itemid FROM critical_lab_definitions)
  ),
  general_critical_labs AS (
    SELECT
      gl.itemid
    FROM general_labs AS gl
    INNER JOIN critical_lab_definitions AS def ON gl.itemid = def.itemid
    WHERE (def.critical_low IS NOT NULL AND gl.valuenum < def.critical_low)
       OR (def.critical_high IS NOT NULL AND gl.valuenum > def.critical_high)
  )
  SELECT
    SAFE_DIVIDE(
      (SELECT COUNT(*) FROM general_critical_labs),
      (SELECT COUNT(*) FROM general_labs)
    ) AS general_population_critical_lab_rate
)
SELECT
  t_out.p90_instability_score,
  t_out.top_tier_mortality_rate,
  t_out.top_tier_avg_los_days,
  t_rate.top_tier_critical_lab_rate,
  g_rate.general_population_critical_lab_rate
FROM
  top_tier_outcomes AS t_out,
  top_tier_rate AS t_rate,
  general_population_rate AS g_rate;
