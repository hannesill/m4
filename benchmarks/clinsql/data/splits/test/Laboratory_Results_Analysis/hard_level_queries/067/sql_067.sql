WITH
-- CTE 1: Define the base population of interest: all inpatients aged 53-63.
base_admissions AS (
  SELECT
    adm.hadm_id,
    adm.subject_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    p.gender,
    (EXTRACT(YEAR FROM adm.admittime) - p.anchor_year) + p.anchor_age AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON adm.subject_id = p.subject_id
  WHERE
    (EXTRACT(YEAR FROM adm.admittime) - p.anchor_year) + p.anchor_age BETWEEN 53 AND 63
),

-- CTE 2: Identify the specific target cohort: female patients with an ACS diagnosis.
acs_cohort AS (
  SELECT DISTINCT
    b.hadm_id,
    b.subject_id,
    b.admittime,
    b.dischtime,
    b.hospital_expire_flag,
    SAFE.DATETIME_DIFF(b.dischtime, b.admittime, DAY) AS los_days
  FROM
    base_admissions AS b
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON b.hadm_id = dx.hadm_id
  WHERE
    b.gender = 'F'
    AND (
      (dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code = '4111'))
      OR (dx.icd_version = 10 AND (dx.icd_code LIKE 'I21%' OR dx.icd_code LIKE 'I22%' OR dx.icd_code = 'I200'))
    )
),

-- CTE 3: Define the age-matched control cohort by excluding ACS patients from the base population.
control_cohort AS (
  SELECT
    ba.hadm_id
  FROM
    base_admissions AS ba
  LEFT JOIN
    acs_cohort AS acs
    ON ba.hadm_id = acs.hadm_id
  WHERE
    acs.hadm_id IS NULL
),

-- CTE 4: Identify all relevant lab events within the first 72 hours for the base population,
-- flag them if they are critical, and assign a standardized category.
critical_events AS (
  SELECT
    le.hadm_id,
    CASE
      WHEN le.itemid IN (50824, 50983) THEN 'Sodium'
      WHEN le.itemid IN (50822, 50971) THEN 'Potassium'
      WHEN le.itemid IN (50912) THEN 'Creatinine'
      WHEN le.itemid IN (51301, 51300) THEN 'WBC'
      WHEN le.itemid IN (50813) THEN 'Lactate'
      WHEN le.itemid IN (51003) THEN 'Troponin-T'
      WHEN le.itemid IN (50868) THEN 'Anion Gap'
      WHEN le.itemid = 50931 THEN 'Glucose' -- Added per prompt
      WHEN le.itemid = 51006 THEN 'BUN'       -- Added per prompt
    END AS lab_category
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN
    base_admissions AS ba
    ON le.hadm_id = ba.hadm_id
    AND le.charttime BETWEEN ba.admittime AND DATETIME_ADD(ba.admittime, INTERVAL 72 HOUR)
  WHERE
    le.valuenum IS NOT NULL AND (
      (le.itemid IN (50824, 50983) AND (le.valuenum < 125 OR le.valuenum > 155)) -- Sodium (mEq/L)
      OR (le.itemid IN (50822, 50971) AND (le.valuenum < 2.5 OR le.valuenum > 6.0)) -- Potassium (mEq/L)
      OR (le.itemid IN (50912) AND le.valuenum > 2.0) -- Creatinine (mg/dL)
      OR (le.itemid IN (51301, 51300) AND (le.valuenum < 2.0 OR le.valuenum > 20.0)) -- WBC (K/uL)
      OR (le.itemid IN (50813) AND le.valuenum > 4.0) -- Lactate (mmol/L)
      OR (le.itemid IN (51003) AND le.valuenum > 0.1) -- Troponin-T (ng/mL)
      OR (le.itemid IN (50868) AND le.valuenum > 20) -- Anion Gap (mEq/L)
      OR (le.itemid = 50931 AND (le.valuenum < 60 OR le.valuenum > 400)) -- Glucose (mg/dL)
      OR (le.itemid = 51006 AND le.valuenum > 40) -- BUN (mg/dL)
    )
),

-- CTE 5: Calculate the instability score for each patient in the ACS cohort.
acs_instability_scores AS (
  SELECT
    acs.hadm_id,
    acs.los_days,
    acs.hospital_expire_flag,
    COALESCE(COUNT(DISTINCT ce.lab_category), 0) AS instability_score
  FROM
    acs_cohort AS acs
  LEFT JOIN
    critical_events AS ce
    ON acs.hadm_id = ce.hadm_id
  GROUP BY
    acs.hadm_id,
    acs.los_days,
    acs.hospital_expire_flag
),

-- CTE 6: Stratify the ACS cohort into quartiles based on their instability score.
acs_quartiles AS (
  SELECT
    hadm_id,
    los_days,
    hospital_expire_flag,
    instability_score,
    NTILE(4) OVER (ORDER BY instability_score) AS instability_quartile
  FROM
    acs_instability_scores
),

-- CTE 7: Summarize outcomes for each quartile of the ACS cohort.
acs_quartile_summary AS (
  SELECT
    instability_quartile,
    COUNT(hadm_id) AS num_patients,
    AVG(instability_score) AS avg_instability_score,
    MIN(instability_score) AS min_score,
    MAX(instability_score) AS max_score,
    AVG(los_days) AS avg_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_pct
  FROM
    acs_quartiles
  GROUP BY
    instability_quartile
),

-- PART 2: Comparison of Critical Lab Rates

-- CTE 8: Count patients in each cohort (ACS vs. Control) who had a specific critical lab event.
cohort_critical_counts AS (
  SELECT
    ce.lab_category,
    'ACS_Female_53_63' AS cohort,
    COUNT(DISTINCT ce.hadm_id) AS num_patients_with_critical_event
  FROM critical_events AS ce
  WHERE ce.hadm_id IN (SELECT hadm_id FROM acs_cohort)
  GROUP BY ce.lab_category
  UNION ALL
  SELECT
    ce.lab_category,
    'Control_Age_Matched' AS cohort,
    COUNT(DISTINCT ce.hadm_id) AS num_patients_with_critical_event
  FROM critical_events AS ce
  WHERE ce.hadm_id IN (SELECT hadm_id FROM control_cohort)
  GROUP BY ce.lab_category
),

-- CTE 9: Get total patient counts for each cohort for rate calculation.
cohort_totals AS (
  SELECT
    'ACS_Female_53_63' AS cohort,
    COUNT(DISTINCT hadm_id) AS total_patients
  FROM acs_cohort
  UNION ALL
  SELECT
    'Control_Age_Matched' AS cohort,
    COUNT(DISTINCT hadm_id) AS total_patients
  FROM control_cohort
),

-- CTE 10: Calculate and pivot the critical lab rates for easy comparison.
comparison_rates AS (
  SELECT
    ccc.lab_category,
    MAX(CASE WHEN ccc.cohort = 'ACS_Female_53_63' THEN SAFE_DIVIDE(ccc.num_patients_with_critical_event, ct.total_patients) * 100 ELSE 0 END) AS acs_rate_pct,
    MAX(CASE WHEN ccc.cohort = 'Control_Age_Matched' THEN SAFE_DIVIDE(ccc.num_patients_with_critical_event, ct.total_patients) * 100 ELSE 0 END) AS control_rate_pct
  FROM
    cohort_critical_counts AS ccc
  INNER JOIN
    cohort_totals AS ct
    ON ccc.cohort = ct.cohort
  GROUP BY
    ccc.lab_category
)

-- FINAL OUTPUT: Combine both analyses into a single long-format table.
-- A sort_order column is added to group the two different analyses in the output.
SELECT
  1 AS sort_order,
  CAST(instability_quartile AS STRING) AS stratum,
  'Number of Patients' AS metric_name,
  CAST(num_patients AS FLOAT64) AS metric_value
FROM acs_quartile_summary
UNION ALL
SELECT
  1 AS sort_order,
  CAST(instability_quartile AS STRING) AS stratum,
  'Avg Instability Score' AS metric_name,
  avg_instability_score
FROM acs_quartile_summary
UNION ALL
SELECT
  1 AS sort_order,
  CAST(instability_quartile AS STRING) AS stratum,
  'Min Score in Quartile' AS metric_name,
  CAST(min_score AS FLOAT64)
FROM acs_quartile_summary
UNION ALL
SELECT
  1 AS sort_order,
  CAST(instability_quartile AS STRING) AS stratum,
  'Max Score in Quartile' AS metric_name,
  CAST(max_score AS FLOAT64)
FROM acs_quartile_summary
UNION ALL
SELECT
  1 AS sort_order,
  CAST(instability_quartile AS STRING) AS stratum,
  'Avg Length of Stay (Days)' AS metric_name,
  avg_los_days
FROM acs_quartile_summary
UNION ALL
SELECT
  1 AS sort_order,
  CAST(instability_quartile AS STRING) AS stratum,
  'In-Hospital Mortality Rate (%)' AS metric_name,
  mortality_rate_pct
FROM acs_quartile_summary

UNION ALL

SELECT
  2 AS sort_order,
  lab_category AS stratum,
  'ACS Cohort Rate (%)' AS metric_name,
  acs_rate_pct AS metric_value
FROM comparison_rates
UNION ALL
SELECT
  2 AS sort_order,
  lab_category AS stratum,
  'Control Cohort Rate (%)' AS metric_name,
  control_rate_pct AS metric_value
-- FIX: Added the missing FROM clause below, which was the cause of the original error.
FROM comparison_rates
ORDER BY
  sort_order,
  stratum,
  metric_name;
