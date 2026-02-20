WITH
  BaseAdmissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.deathtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age AS age_at_admission,
      GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) BETWEEN 73 AND 83
  ),
  DiagnosisFeatures AS (
    SELECT
      b.hadm_id,
      MAX(CASE
        WHEN d.icd_version = 9 AND d.icd_code LIKE '48%' THEN 1
        WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'J12' AND 'J18' THEN 1
        ELSE 0
      END) AS has_pneumonia,
      MAX(CASE
        WHEN d.icd_version = 9 AND d.icd_code IN ('995.92', '785.52', '427.5', '518.81', '518.82', 'V58.11', '786.03', '038.9') THEN 1
        WHEN d.icd_version = 9 AND d.icd_code LIKE '410%' THEN 1
        WHEN d.icd_version = 10 AND d.icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'I46.9', 'J96.00', 'J80', 'Z51.11', 'R06.03') THEN 1
        WHEN d.icd_version = 10 AND d.icd_code LIKE 'I21%' THEN 1
        ELSE 0
      END) AS has_major_complication,
      COUNT(DISTINCT d.icd_code) AS comorbidity_count
    FROM
      BaseAdmissions AS b
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON b.hadm_id = d.hadm_id
    GROUP BY
      b.hadm_id
  ),
  HighComorbidityThreshold AS (
    SELECT
      APPROX_QUANTILES(comorbidity_count, 100)[OFFSET(75)] AS threshold
    FROM
      DiagnosisFeatures
  ),
  TargetCohort AS (
    SELECT
      ba.subject_id,
      ba.hadm_id,
      ba.age_at_admission,
      ba.los_days,
      ba.hospital_expire_flag,
      ba.admittime,
      ba.deathtime,
      df.has_major_complication,
      df.comorbidity_count
    FROM
      BaseAdmissions AS ba
    JOIN
      DiagnosisFeatures AS df
      ON ba.hadm_id = df.hadm_id
    WHERE
      df.has_pneumonia = 1
      AND df.comorbidity_count >= (SELECT threshold FROM HighComorbidityThreshold)
  ),
  RiskScoreComponents AS (
    SELECT
      subject_id,
      hadm_id,
      age_at_admission,
      los_days,
      comorbidity_count,
      has_major_complication,
      hospital_expire_flag,
      admittime,
      deathtime,
      (SAFE_DIVIDE(age_at_admission - MIN(age_at_admission) OVER(), MAX(age_at_admission) OVER() - MIN(age_at_admission) OVER()) * 100) AS age_score,
      (SAFE_DIVIDE(los_days - MIN(los_days) OVER(), MAX(los_days) OVER() - MIN(los_days) OVER()) * 100) AS los_score,
      (SAFE_DIVIDE(comorbidity_count - MIN(comorbidity_count) OVER(), MAX(comorbidity_count) OVER() - MIN(comorbidity_count) OVER()) * 100) AS comorbidity_score
    FROM
      TargetCohort
  ),
  RankedScores AS (
    SELECT
      *,
      (0.4 * COALESCE(age_score, 0)) + (0.4 * COALESCE(comorbidity_score, 0)) + (0.2 * COALESCE(los_score, 0)) AS composite_risk_score,
      PERCENT_RANK() OVER (ORDER BY (0.4 * COALESCE(age_score, 0)) + (0.4 * COALESCE(comorbidity_score, 0)) + (0.2 * COALESCE(los_score, 0))) AS risk_percentile_rank
    FROM
      RiskScoreComponents
  ),
  CohortSummary AS (
    SELECT
      COUNT(DISTINCT subject_id) AS total_patients,
      AVG(hospital_expire_flag) * 100 AS in_hospital_mortality_rate_pct,
      AVG(has_major_complication) * 100 AS major_complication_rate_pct,
      (
        SELECT
          PERCENTILE_CONT(DATETIME_DIFF(deathtime, admittime, DAY), 0.5) OVER()
        FROM
          TargetCohort
        WHERE
          hospital_expire_flag = 1 AND deathtime IS NOT NULL
        LIMIT 1
      ) AS median_survival_days_for_deceased
    FROM
      TargetCohort
  )
SELECT
  rs.subject_id,
  rs.hadm_id,
  rs.age_at_admission,
  rs.comorbidity_count,
  ROUND(rs.los_days, 1) AS length_of_stay_days,
  rs.hospital_expire_flag,
  rs.has_major_complication,
  ROUND(rs.composite_risk_score, 2) AS composite_risk_score,
  ROUND(rs.risk_percentile_rank * 100, 2) AS risk_percentile_rank,
  cs.total_patients AS cohort_total_patients,
  ROUND(cs.in_hospital_mortality_rate_pct, 2) AS cohort_in_hospital_mortality_pct,
  ROUND(cs.major_complication_rate_pct, 2) AS cohort_major_complication_pct,
  ROUND(cs.median_survival_days_for_deceased, 1) AS cohort_median_survival_days_deceased
FROM
  RankedScores AS rs
CROSS JOIN
  CohortSummary AS cs
ORDER BY
  rs.composite_risk_score DESC;
