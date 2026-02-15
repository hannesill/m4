WITH
  admissions_base AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      pat.gender,
      pat.anchor_age + DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission,
      adm.hospital_expire_flag,
      CASE
        WHEN pat.dod IS NOT NULL AND adm.dischtime IS NOT NULL
          AND DATETIME_DIFF(pat.dod, adm.dischtime, DAY) BETWEEN 0 AND 90
        THEN 1
        ELSE 0
      END AS mortality_90_day_flag,
      DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    WHERE
      adm.admittime IS NOT NULL AND adm.dischtime IS NOT NULL
  ),
  diagnoses_flags AS (
    SELECT
      hadm_id,
      icd_code,
      icd_version,
      CASE
        WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 5) IN ('45340', '45341', '45342'))
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I824', 'I825', 'I826'))
        THEN 1
        ELSE 0
      END AS is_dvt_diag,
      CASE
        WHEN
          (icd_version = 9 AND (
            icd_code IN ('995.92', '785.52', '038.9', '427.5', '518.81', '518.82')
            OR SUBSTR(icd_code, 1, 3) = '410'
          ))
          OR
          (icd_version = 10 AND (
            icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'I46.9', 'J96.00', 'J80')
            OR SUBSTR(icd_code, 1, 3) = 'I21'
          ))
        THEN 1
        ELSE 0
      END AS is_major_complication_diag
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  ),
  admission_features AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT icd_code) AS diagnosis_count,
      MAX(is_dvt_diag) AS has_dvt,
      SUM(is_major_complication_diag) AS major_complication_count,
      MAX(is_major_complication_diag) AS has_major_complication
    FROM
      diagnoses_flags
    GROUP BY
      hadm_id
  ),
  full_cohort_data AS (
    SELECT
      ab.subject_id,
      ab.hadm_id,
      ab.age_at_admission,
      ab.mortality_90_day_flag,
      af.has_major_complication,
      CASE WHEN ab.hospital_expire_flag = 0 THEN ab.los_days ELSE NULL END AS survivor_los_days,
      (af.diagnosis_count + (af.major_complication_count * 10)) AS risk_score,
      CASE
        WHEN
          ab.gender = 'M'
          AND ab.age_at_admission BETWEEN 71 AND 81
          AND af.has_dvt = 1
          AND af.diagnosis_count > 5
        THEN 'Target_DVT_High_Comorbidity'
        ELSE 'General_Inpatient_Population'
      END AS cohort_name
    FROM
      admissions_base AS ab
    INNER JOIN
      admission_features AS af
      ON ab.hadm_id = af.hadm_id
  )
SELECT
  cohort_name,
  COUNT(DISTINCT subject_id) AS total_patients,
  APPROX_QUANTILES(risk_score, 100)[OFFSET(50)] AS median_risk_score,
  (APPROX_QUANTILES(risk_score, 100)[OFFSET(75)] - APPROX_QUANTILES(risk_score, 100)[OFFSET(25)]) AS iqr_risk_score,
  AVG(mortality_90_day_flag) * 100 AS mortality_90_day_rate_pct,
  AVG(has_major_complication) * 100 AS major_complication_rate_pct,
  AVG(survivor_los_days) AS avg_survivor_los_days,
  CASE
    WHEN cohort_name = 'Target_DVT_High_Comorbidity'
    THEN (
      WITH ranked_target_cohort AS (
        SELECT
          age_at_admission,
          PERCENT_RANK() OVER (ORDER BY risk_score ASC) * 100 AS risk_percentile
        FROM full_cohort_data
        WHERE cohort_name = 'Target_DVT_High_Comorbidity'
      )
      SELECT
        AVG(risk_percentile)
      FROM
        ranked_target_cohort
      WHERE
        age_at_admission = 76
    )
    ELSE NULL
  END AS matched_profile_risk_percentile
FROM
  full_cohort_data
GROUP BY
  cohort_name
ORDER BY
  total_patients ASC;
