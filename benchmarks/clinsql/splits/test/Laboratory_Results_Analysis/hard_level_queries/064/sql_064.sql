WITH
age_cohort AS (
  SELECT
    adm.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year + pat.anchor_age) AS age_at_admission,
    pat.gender
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  WHERE
    (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year + pat.anchor_age) BETWEEN 65 AND 75
),
pancreatitis_cohort AS (
  SELECT DISTINCT
    ac.subject_id,
    ac.hadm_id,
    ac.admittime,
    ac.dischtime,
    ac.hospital_expire_flag
  FROM
    age_cohort AS ac
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON ac.hadm_id = dx.hadm_id
  WHERE
    ac.gender = 'F'
    AND (
      dx.icd_code = '5770' AND dx.icd_version = 9
      OR STARTS_WITH(dx.icd_code, 'K85') AND dx.icd_version = 10
    )
),
control_cohort AS (
  SELECT
    subject_id,
    hadm_id
  FROM
    age_cohort
),
critical_labs AS (
  SELECT
    le.hadm_id,
    le.itemid,
    CASE
      WHEN le.itemid = 51301 AND (le.valuenum < 2 OR le.valuenum > 20) THEN 1
      WHEN le.itemid = 51265 AND le.valuenum < 50 THEN 1
      WHEN le.itemid = 51222 AND le.valuenum < 7 THEN 1
      WHEN le.itemid = 50983 AND (le.valuenum < 125 OR le.valuenum > 155) THEN 1
      WHEN le.itemid = 50971 AND (le.valuenum < 3.0 OR le.valuenum > 6.0) THEN 1
      WHEN le.itemid = 50912 AND le.valuenum > 3.0 THEN 1
      WHEN le.itemid = 50931 AND (le.valuenum < 60 OR le.valuenum > 400) THEN 1
      WHEN le.itemid = 51006 AND le.valuenum > 40 THEN 1
      WHEN le.itemid = 50813 AND le.valuenum > 4.0 THEN 1
      WHEN le.itemid = 50956 AND le.valuenum > 600 THEN 1
      WHEN le.itemid = 50885 AND le.valuenum > 4.0 THEN 1
      WHEN le.itemid = 51003 AND le.valuenum > 0.1 THEN 1
      ELSE 0
    END AS is_critical
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
  WHERE
    le.hadm_id IS NOT NULL
    AND le.valuenum IS NOT NULL
    AND le.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 48 HOUR)
    AND le.itemid IN (
      51301,
      51265,
      51222,
      50983,
      50971,
      50912,
      50931,
      51006,
      50813,
      50956,
      50885,
      51003
    )
),
instability_scores AS (
  SELECT
    pc.hadm_id,
    pc.hospital_expire_flag,
    TIMESTAMP_DIFF(pc.dischtime, pc.admittime, DAY) AS los_days,
    COUNT(DISTINCT CASE WHEN cl.is_critical = 1 THEN cl.itemid END) AS instability_score
  FROM
    pancreatitis_cohort AS pc
  LEFT JOIN
    critical_labs AS cl
    ON pc.hadm_id = cl.hadm_id
  GROUP BY
    pc.hadm_id, pc.hospital_expire_flag, pc.dischtime, pc.admittime
),
ranked_scores AS (
  SELECT
    hadm_id,
    instability_score,
    los_days,
    hospital_expire_flag,
    NTILE(5) OVER (ORDER BY instability_score) AS score_quintile
  FROM
    instability_scores
),
quintile_outcomes AS (
  SELECT
    score_quintile,
    COUNT(hadm_id) AS num_patients,
    AVG(instability_score) AS avg_instability_score,
    AVG(los_days) AS avg_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
  FROM
    ranked_scores
  GROUP BY
    score_quintile
),
critical_lab_frequencies AS (
  WITH
  patient_critical_events AS (
    SELECT DISTINCT
      hadm_id,
      itemid
    FROM critical_labs
    WHERE is_critical = 1
  ),
  cohort_patient_counts AS (
    SELECT 'Pancreatitis' as cohort_type, CAST(COUNT(*) AS FLOAT64) as total_patients FROM pancreatitis_cohort
    UNION ALL
    SELECT 'Control' as cohort_type, CAST(COUNT(*) AS FLOAT64) as total_patients FROM control_cohort
  )
  SELECT
    pce.itemid,
    COUNT(DISTINCT CASE WHEN pc.hadm_id IS NOT NULL THEN pce.hadm_id END) / MAX(CASE WHEN cpc.cohort_type = 'Pancreatitis' THEN cpc.total_patients END) AS pancreatitis_critical_rate,
    COUNT(DISTINCT CASE WHEN cc.hadm_id IS NOT NULL THEN pce.hadm_id END) / MAX(CASE WHEN cpc.cohort_type = 'Control' THEN cpc.total_patients END) AS control_critical_rate
  FROM
    patient_critical_events AS pce
  LEFT JOIN
    pancreatitis_cohort AS pc ON pce.hadm_id = pc.hadm_id
  LEFT JOIN
    control_cohort AS cc ON pce.hadm_id = cc.hadm_id
  CROSS JOIN
    cohort_patient_counts AS cpc
  GROUP BY
    pce.itemid
)
SELECT
  1 AS part,
  1 AS sort_order,
  'Quintile' AS column_1,
  'Patient Count' AS column_2,
  'Avg Instability Score' AS column_3,
  'Avg LOS (Days)' AS column_4,
  'Mortality Rate (%)' AS column_5
UNION ALL
SELECT
  1 AS part,
  2 AS sort_order,
  CAST(score_quintile AS STRING),
  CAST(num_patients AS STRING),
  CAST(ROUND(avg_instability_score, 2) AS STRING),
  CAST(ROUND(avg_los_days, 1) AS STRING),
  CAST(ROUND(mortality_rate * 100, 2) AS STRING)
FROM
  quintile_outcomes
UNION ALL
SELECT 2, 1, '---', '---', '---', '---', '---'
UNION ALL
SELECT
  3 AS part,
  1 AS sort_order,
  'CRITICAL LAB FREQUENCY COMPARISON (First 48h)',
  NULL,
  NULL,
  NULL,
  NULL
UNION ALL
SELECT
  3 AS part,
  2 AS sort_order,
  'Lab Test',
  '% Pancreatitis Pts w/ Critical',
  '% Control Pts w/ Critical (Age-Matched)',
  NULL,
  NULL
UNION ALL
SELECT
  3 AS part,
  3 AS sort_order,
  d_lab.label,
  CAST(ROUND(freq.pancreatitis_critical_rate * 100, 2) AS STRING),
  CAST(ROUND(freq.control_critical_rate * 100, 2) AS STRING),
  NULL,
  NULL
FROM
  critical_lab_frequencies AS freq
JOIN
  `physionet-data.mimiciv_3_1_hosp.d_labitems` AS d_lab
  ON freq.itemid = d_lab.itemid
ORDER BY
  part, sort_order, column_1;
