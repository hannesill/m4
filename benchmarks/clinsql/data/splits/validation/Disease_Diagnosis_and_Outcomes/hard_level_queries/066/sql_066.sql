WITH
base_admissions AS (
  SELECT
    p.subject_id,
    p.gender,
    p.dod,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.deathtime,
    a.hospital_expire_flag,
    DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    a.hadm_id IS NOT NULL
),
diagnoses_categorized AS (
  SELECT
    b.subject_id,
    b.hadm_id,
    b.age_at_admission,
    b.gender,
    b.dod,
    b.admittime,
    b.dischtime,
    b.hospital_expire_flag,
    d.icd_code,
    d.icd_version,
    CASE
      WHEN (d.icd_version = 9 AND d.icd_code LIKE '4151%') OR (d.icd_version = 10 AND d.icd_code LIKE 'I26%')
      THEN 1 ELSE 0
    END AS has_pe_flag,
    CASE
      WHEN (d.icd_version = 9 AND d.icd_code LIKE '584%') OR (d.icd_version = 10 AND d.icd_code LIKE 'N17%')
      THEN 1 ELSE 0
    END AS has_aki_flag,
    CASE
      WHEN (d.icd_version = 9 AND d.icd_code = '51882') OR (d.icd_version = 10 AND d.icd_code = 'J80')
      THEN 1 ELSE 0
    END AS has_ards_flag,
    CASE
      WHEN
        (d.icd_version = 10 AND d.icd_code IN ('R68.81', 'R57.0')) OR (d.icd_version = 9 AND d.icd_code IN ('99592', '78552')) OR
        (d.icd_version = 10 AND d.icd_code IN ('R65.21', 'A41.9')) OR (d.icd_version = 9 AND d.icd_code IN ('99592', '0389')) OR
        (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code = 'I46.9')) OR (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4275')) OR
        (d.icd_version = 10 AND d.icd_code IN ('J96.00', 'J80')) OR (d.icd_version = 9 AND d.icd_code IN ('51881', '51882')) OR
        (d.icd_version = 10 AND d.icd_code IN ('Z51.11', 'R06.03')) OR (d.icd_version = 9 AND d.icd_code IN ('V5811', '78603'))
      THEN 1 ELSE 0
    END AS is_critical_illness_flag
  FROM
    base_admissions AS b
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON b.hadm_id = d.hadm_id
),
admission_level_features AS (
  SELECT
    subject_id,
    hadm_id,
    age_at_admission,
    gender,
    admittime,
    dischtime,
    dod,
    hospital_expire_flag,
    MAX(has_pe_flag) AS has_pe,
    MAX(has_aki_flag) AS has_aki,
    MAX(has_ards_flag) AS has_ards,
    (COUNT(DISTINCT icd_code) * 1) + (SUM(is_critical_illness_flag) * 5) AS risk_score,
    GREATEST(0, DATETIME_DIFF(dischtime, admittime, DAY)) AS los_days,
    CASE
      WHEN hospital_expire_flag = 1 THEN 1
      WHEN dod IS NOT NULL AND DATETIME_DIFF(dod, dischtime, DAY) BETWEEN 0 AND 90 THEN 1
      ELSE 0
    END AS is_90_day_mortality
  FROM
    diagnoses_categorized
  GROUP BY
    subject_id, hadm_id, age_at_admission, gender, admittime, dischtime, dod, hospital_expire_flag
),
high_comorbidity_threshold AS (
  SELECT
    APPROX_QUANTILES(risk_score, 100)[OFFSET(75)] AS p75_risk_score
  FROM
    admission_level_features
  WHERE
    gender = 'M'
    AND age_at_admission BETWEEN 81 AND 91
),
cohorts_identified AS (
  SELECT
    f.*,
    CASE
      WHEN
        f.gender = 'M'
        AND f.age_at_admission BETWEEN 81 AND 91
        AND f.has_pe = 1
        AND f.risk_score > (SELECT p75_risk_score FROM high_comorbidity_threshold)
      THEN 1 ELSE 0
    END AS is_target_cohort
  FROM
    admission_level_features AS f
),
cohort_comparison AS (
  SELECT
    'Target_PE_High_Comorbidity' AS cohort_name,
    COUNT(DISTINCT hadm_id) AS number_of_patients,
    AVG(risk_score) AS mean_risk_score,
    AVG(is_90_day_mortality) * 100 AS mortality_rate_90_day_perc,
    AVG(has_aki) * 100 AS aki_rate_perc,
    AVG(has_ards) * 100 AS ards_rate_perc,
    AVG(CASE WHEN is_90_day_mortality = 0 THEN los_days END) AS survivor_mean_los_days
  FROM
    cohorts_identified
  WHERE
    is_target_cohort = 1
  UNION ALL
  SELECT
    'General_Inpatient_Population' AS cohort_name,
    COUNT(DISTINCT hadm_id) AS number_of_patients,
    AVG(risk_score) AS mean_risk_score,
    AVG(is_90_day_mortality) * 100 AS mortality_rate_90_day_perc,
    AVG(has_aki) * 100 AS aki_rate_perc,
    AVG(has_ards) * 100 AS ards_rate_perc,
    AVG(CASE WHEN is_90_day_mortality = 0 THEN los_days END) AS survivor_mean_los_days
  FROM
    cohorts_identified
),
target_cohort_percentile AS (
  SELECT
    AVG(risk_score) AS matched_profile_avg_risk_score,
    AVG(risk_percentile) * 100 AS matched_profile_risk_percentile
  FROM (
    SELECT
      risk_score,
      PERCENT_RANK() OVER (ORDER BY risk_score) AS risk_percentile
    FROM
      cohorts_identified
    WHERE
      is_target_cohort = 1
  )
)
SELECT
  cc.cohort_name,
  cc.number_of_patients,
  ROUND(cc.mean_risk_score, 2) AS mean_risk_score,
  ROUND(cc.mortality_rate_90_day_perc, 2) AS mortality_rate_90_day_perc,
  ROUND(cc.aki_rate_perc, 2) AS aki_rate_perc,
  ROUND(cc.ards_rate_perc, 2) AS ards_rate_perc,
  ROUND(cc.survivor_mean_los_days, 2) AS survivor_mean_los_days,
  CASE
    WHEN cc.cohort_name = 'Target_PE_High_Comorbidity'
    THEN ROUND(tcp.matched_profile_avg_risk_score, 2)
    ELSE NULL
  END AS matched_profile_avg_risk_score,
  CASE
    WHEN cc.cohort_name = 'Target_PE_High_Comorbidity'
    THEN ROUND(tcp.matched_profile_risk_percentile, 2)
    ELSE NULL
  END AS matched_profile_risk_percentile
FROM
  cohort_comparison AS cc
CROSS JOIN
  target_cohort_percentile AS tcp
ORDER BY
  cc.number_of_patients DESC;
