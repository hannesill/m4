WITH
  base_patients_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      p.gender,
      p.dod,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
  ),
  aki_diagnoses AS (
    SELECT DISTINCT
      hadm_id,
      1 AS is_aki
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '584')
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'N17')
  ),
  ards_diagnoses AS (
    SELECT DISTINCT
      hadm_id,
      1 AS is_ards
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND icd_code = '51882')
      OR (icd_version = 10 AND icd_code = 'J80')
  ),
  comorbidities AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT icd_code) AS comorbidity_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  cohort_with_features AS (
    SELECT
      bpa.hadm_id,
      bpa.hospital_expire_flag,
      GREATEST(0, DATETIME_DIFF(bpa.dischtime, bpa.admittime, DAY)) AS los_days,
      CASE
        WHEN bpa.dod IS NOT NULL AND DATE_DIFF(DATE(bpa.dod), DATE(bpa.dischtime), DAY) BETWEEN 0 AND 30
        THEN 1
        ELSE 0
      END AS mortality_30day_flag,
      COALESCE(ards.is_ards, 0) AS is_ards,
      COALESCE(como.comorbidity_count, 0) AS comorbidity_count
    FROM
      base_patients_admissions AS bpa
    INNER JOIN
      aki_diagnoses AS aki
      ON bpa.hadm_id = aki.hadm_id
    LEFT JOIN
      ards_diagnoses AS ards
      ON bpa.hadm_id = ards.hadm_id
    LEFT JOIN
      comorbidities AS como
      ON bpa.hadm_id = como.hadm_id
    WHERE
      bpa.gender = 'F'
      AND bpa.age_at_admission BETWEEN 40 AND 50
  ),
  risk_scored_cohort AS (
    SELECT
      *,
      (comorbidity_count * 5) + (is_ards * 50) AS composite_risk_score
    FROM
      cohort_with_features
  ),
  quintiled_cohort AS (
    SELECT
      *,
      NTILE(5) OVER (ORDER BY composite_risk_score ASC, hadm_id) AS risk_quintile
    FROM
      risk_scored_cohort
  )
SELECT
  risk_quintile,
  COUNT(*) AS total_patients,
  ROUND(AVG(mortality_30day_flag) * 100, 2) AS mortality_30day_rate_pct,
  ROUND(AVG(is_ards) * 100, 2) AS ards_co_occurrence_rate_pct,
  APPROX_QUANTILES(IF(hospital_expire_flag = 0, los_days, NULL), 100)[OFFSET(50)] AS median_survivor_los_days
FROM
  quintiled_cohort
GROUP BY
  risk_quintile
ORDER BY
  risk_quintile;
