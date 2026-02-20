WITH
patient_base AS (
  SELECT
    p.subject_id,
    p.anchor_age,
    p.dod,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 59 AND 69
),
diagnoses_flags AS (
  SELECT
    pb.hadm_id,
    d.icd_code,
    d.icd_version,
    CASE
      WHEN (d.icd_version = 10 AND d.icd_code LIKE 'I26%')
           OR (d.icd_version = 9 AND d.icd_code LIKE '415.1%')
      THEN 1 ELSE 0
    END AS is_pe,
    CASE
      WHEN (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code = 'I46.9'))
           OR (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '427.5'))
      THEN 1 ELSE 0
    END AS is_cardio_comp,
    CASE
      WHEN (d.icd_version = 10 AND d.icd_code LIKE 'I6%')
           OR (d.icd_version = 9 AND d.icd_code LIKE '43%')
      THEN 1 ELSE 0
    END AS is_neuro_comp,
    CASE
      WHEN
        (d.icd_version = 10 AND d.icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'J96.00', 'J80', 'Z51.11', 'R06.03', 'I46.9'))
        OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
        OR (d.icd_version = 9 AND d.icd_code IN ('995.92', '785.52', '038.9', '518.81', '518.82', 'V58.11', '786.03', '427.5'))
        OR (d.icd_version = 9 AND d.icd_code LIKE '410%')
      THEN 1 ELSE 0
    END AS is_comorbidity_dx
  FROM
    patient_base AS pb
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON pb.hadm_id = d.hadm_id
),
admission_level_features AS (
  SELECT
    pb.subject_id,
    pb.hadm_id,
    pb.admittime,
    pb.dischtime,
    pb.dod,
    pb.hospital_expire_flag,
    MAX(df.is_pe) AS has_pe,
    MAX(df.is_cardio_comp) AS has_cardio_comp,
    MAX(df.is_neuro_comp) AS has_neuro_comp,
    COUNT(DISTINCT CASE WHEN df.is_comorbidity_dx = 1 THEN df.icd_code END) AS comorbidity_dx_count,
    COUNT(DISTINCT df.icd_code) AS total_dx_count,
    DATETIME_DIFF(pb.dischtime, pb.admittime, DAY) AS los_days,
    CASE
      WHEN pb.hospital_expire_flag = 1 THEN 1
      WHEN pb.dod IS NOT NULL AND DATE_DIFF(CAST(pb.dod AS DATE), CAST(pb.dischtime AS DATE), DAY) BETWEEN 0 AND 30 THEN 1
      ELSE 0
    END AS mortality_30day
  FROM
    patient_base AS pb
  LEFT JOIN
    diagnoses_flags AS df
    ON pb.hadm_id = df.hadm_id
  GROUP BY
    pb.subject_id, pb.hadm_id, pb.admittime, pb.dischtime, pb.dod, pb.hospital_expire_flag
),
cohort_definition_and_scoring AS (
  SELECT
    alf.*,
    LEAST(100, (alf.comorbidity_dx_count * 15) + alf.total_dx_count) AS comorbidity_risk_score,
    CASE
      WHEN alf.comorbidity_dx_count >= 2 OR alf.total_dx_count > 15 THEN 1
      ELSE 0
    END AS is_high_comorbidity_burden
  FROM
    admission_level_features AS alf
),
final_cohorts AS (
  SELECT
    cds.*,
    CASE
      WHEN cds.has_pe = 1 AND cds.is_high_comorbidity_burden = 1 THEN 'Target (PE w/ High Comorbidity)'
      ELSE 'Control (General Inpatient)'
    END AS cohort
  FROM
    cohort_definition_and_scoring AS cds
),
cohort_aggregates AS (
  SELECT
    cohort,
    COUNT(DISTINCT hadm_id) AS cohort_size,
    AVG(comorbidity_risk_score) AS mean_risk_score,
    AVG(mortality_30day) * 100 AS mortality_30day_rate_pct,
    AVG(has_cardio_comp) * 100 AS cardio_complication_rate_pct,
    AVG(has_neuro_comp) * 100 AS neuro_complication_rate_pct,
    AVG(CASE WHEN mortality_30day = 0 THEN los_days END) AS survivor_avg_los_days
  FROM
    final_cohorts
  GROUP BY
    cohort
),
median_target_risk AS (
  SELECT
    APPROX_QUANTILES(comorbidity_risk_score, 2)[OFFSET(1)] AS median_score
  FROM
    final_cohorts
  WHERE
    cohort = 'Target (PE w/ High Comorbidity)'
),
percentile_rank_in_control AS (
  SELECT
    SAFE_DIVIDE(
      COUNTIF(fc.comorbidity_risk_score < mtr.median_score),
      COUNT(fc.hadm_id)
    ) * 100 AS percentile_of_matched_profile_in_control
  FROM
    final_cohorts AS fc,
    median_target_risk AS mtr
  WHERE
    fc.cohort = 'Control (General Inpatient)'
)
SELECT
  ca.cohort,
  ca.cohort_size,
  ROUND(ca.mean_risk_score, 2) AS mean_risk_score,
  ROUND(ca.mortality_30day_rate_pct, 2) AS mortality_30day_rate_pct,
  ROUND(ca.cardio_complication_rate_pct, 2) AS cardio_complication_rate_pct,
  ROUND(ca.neuro_complication_rate_pct, 2) AS neuro_complication_rate_pct,
  ROUND(ca.survivor_avg_los_days, 1) AS survivor_avg_los_days,
  CASE
    WHEN ca.cohort = 'Target (PE w/ High Comorbidity)' THEN ROUND(pr.percentile_of_matched_profile_in_control, 2)
    ELSE NULL
  END AS matched_profile_risk_percentile_vs_control
FROM
  cohort_aggregates AS ca,
  percentile_rank_in_control AS pr
ORDER BY
  ca.cohort DESC;
