WITH
ami_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410') OR
    (icd_version = 10 AND (SUBSTR(icd_code, 1, 3) = 'I21' OR SUBSTR(icd_code, 1, 3) = 'I22'))
),
base_cohorts AS (
  SELECT
    adm.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    (pat.gender = 'F' AND ami.hadm_id IS NOT NULL) AS is_target_ami_group
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  LEFT JOIN ami_admissions AS ami
    ON adm.hadm_id = ami.hadm_id
  WHERE
    (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 90 AND 100
),
critical_events AS (
  SELECT
    bc.hadm_id,
    CASE
      WHEN le.itemid IN (50971, 50822) AND le.valuenum < 3.0 THEN 'critical_hypokalemia'
      WHEN le.itemid IN (50971, 50822) AND le.valuenum > 6.0 THEN 'critical_hyperkalemia'
      WHEN le.itemid IN (50983, 50824) AND le.valuenum < 125 THEN 'critical_hyponatremia'
      WHEN le.itemid IN (50983, 50824) AND le.valuenum > 155 THEN 'critical_hypernatremia'
      WHEN le.itemid = 50912 AND le.valuenum > 2.0 THEN 'critical_creatinine'
      WHEN le.itemid = 50813 AND le.valuenum > 4.0 THEN 'critical_lactate'
      WHEN le.itemid IN (51301, 51300) AND le.valuenum < 2.0 THEN 'critical_leukopenia'
      WHEN le.itemid IN (51301, 51300) AND le.valuenum > 20.0 THEN 'critical_leukocytosis'
      WHEN le.itemid = 51265 AND le.valuenum < 50 THEN 'critical_thrombocytopenia'
      ELSE NULL
    END AS critical_event_type
  FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN base_cohorts AS bc
    ON le.hadm_id = bc.hadm_id
  WHERE
    TIMESTAMP_DIFF(le.charttime, bc.admittime, HOUR) BETWEEN 0 AND 48
    AND le.valuenum IS NOT NULL
),
instability_scores AS (
  SELECT
    hadm_id,
    COUNT(critical_event_type) AS instability_score,
    COUNTIF(critical_event_type IN ('critical_hypokalemia', 'critical_hyperkalemia')) > 0 AS had_critical_potassium,
    COUNTIF(critical_event_type IN ('critical_hyponatremia', 'critical_hypernatremia')) > 0 AS had_critical_sodium,
    COUNTIF(critical_event_type = 'critical_creatinine') > 0 AS had_critical_creatinine,
    COUNTIF(critical_event_type = 'critical_lactate') > 0 AS had_critical_lactate,
    COUNTIF(critical_event_type IN ('critical_leukopenia', 'critical_leukocytosis')) > 0 AS had_critical_wbc,
    COUNTIF(critical_event_type = 'critical_thrombocytopenia') > 0 AS had_critical_platelets
  FROM critical_events
  WHERE critical_event_type IS NOT NULL
  GROUP BY hadm_id
),
cohort_data AS (
  SELECT
    bc.hadm_id,
    bc.is_target_ami_group,
    bc.hospital_expire_flag,
    TIMESTAMP_DIFF(bc.dischtime, bc.admittime, DAY) AS los_days,
    COALESCE(iss.instability_score, 0) AS instability_score,
    COALESCE(iss.had_critical_potassium, FALSE) AS had_critical_potassium,
    COALESCE(iss.had_critical_sodium, FALSE) AS had_critical_sodium,
    COALESCE(iss.had_critical_creatinine, FALSE) AS had_critical_creatinine,
    COALESCE(iss.had_critical_lactate, FALSE) AS had_critical_lactate,
    COALESCE(iss.had_critical_wbc, FALSE) AS had_critical_wbc,
    COALESCE(iss.had_critical_platelets, FALSE) AS had_critical_platelets
  FROM base_cohorts AS bc
  LEFT JOIN instability_scores AS iss
    ON bc.hadm_id = iss.hadm_id
),
ami_p75_score AS (
  SELECT
    APPROX_QUANTILES(instability_score, 100)[OFFSET(75)] AS p75_score
  FROM cohort_data
  WHERE is_target_ami_group IS TRUE
)
SELECT
  'P75 Instability Score (AMI Females 90-100, First 48h)' AS metric,
  CAST((SELECT p75_score FROM ami_p75_score) AS STRING) AS value,
  '--' AS comparison_group,
  '--' AS control_group_value,
  'The 75th percentile of the number of critical lab events in the first 48h for the target cohort.' AS description
UNION ALL
SELECT
  'In-Hospital Mortality Rate' AS metric,
  FORMAT("%.3f", AVG(CAST(cd.hospital_expire_flag AS INT64))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  '--' AS control_group_value,
  'Proportion of patients in the top tier who died during the hospital admission.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Average Length of Stay (Days)' AS metric,
  FORMAT("%.2f", AVG(cd.los_days)) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  '--' AS control_group_value,
  'Average hospital length of stay in days for the top tier group.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Rate of Critical Potassium' AS metric,
  FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(cd.had_critical_potassium), COUNT(cd.hadm_id))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  (SELECT FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(had_critical_potassium), COUNT(hadm_id))) FROM cohort_data) AS control_group_value,
  'Rate of patients with K+ < 3.0 or > 6.0. Control group is all inpatients aged 90-100.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Rate of Critical Sodium' AS metric,
  FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(cd.had_critical_sodium), COUNT(cd.hadm_id))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  (SELECT FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(had_critical_sodium), COUNT(hadm_id))) FROM cohort_data) AS control_group_value,
  'Rate of patients with Na+ < 125 or > 155. Control group is all inpatients aged 90-100.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Rate of Critical Creatinine (>2.0)' AS metric,
  FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(cd.had_critical_creatinine), COUNT(cd.hadm_id))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  (SELECT FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(had_critical_creatinine), COUNT(hadm_id))) FROM cohort_data) AS control_group_value,
  'Rate of patients with Creatinine > 2.0 mg/dL. Control group is all inpatients aged 90-100.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Rate of Critical Lactate (>4.0)' AS metric,
  FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(cd.had_critical_lactate), COUNT(cd.hadm_id))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  (SELECT FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(had_critical_lactate), COUNT(hadm_id))) FROM cohort_data) AS control_group_value,
  'Rate of patients with Lactate > 4.0 mmol/L. Control group is all inpatients aged 90-100.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Rate of Critical WBC' AS metric,
  FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(cd.had_critical_wbc), COUNT(cd.hadm_id))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  (SELECT FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(had_critical_wbc), COUNT(hadm_id))) FROM cohort_data) AS control_group_value,
  'Rate of patients with WBC < 2.0 or > 20.0 K/uL. Control group is all inpatients aged 90-100.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score
UNION ALL
SELECT
  'Rate of Critical Platelets (<50)' AS metric,
  FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(cd.had_critical_platelets), COUNT(cd.hadm_id))) AS value,
  'Top Tier AMI (Score >= P75)' AS comparison_group,
  (SELECT FORMAT("%.3f", SAFE_DIVIDE(COUNTIF(had_critical_platelets), COUNT(hadm_id))) FROM cohort_data) AS control_group_value,
  'Rate of patients with Platelets < 50 K/uL. Control group is all inpatients aged 90-100.' AS description
FROM cohort_data AS cd, ami_p75_score AS ap
WHERE cd.is_target_ami_group IS TRUE AND cd.instability_score >= ap.p75_score;
