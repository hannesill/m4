WITH
  base_patients AS (
    SELECT
      p.subject_id,
      p.anchor_age,
      p.dod
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 68 AND 78
  ),
  admission_details AS (
    SELECT
      bp.subject_id,
      a.hadm_id,
      a.admittime,
      CASE
        WHEN bp.dod IS NOT NULL AND DATETIME_DIFF(bp.dod, a.admittime, DAY) <= 90
        THEN 1
        ELSE 0
      END AS mortality_90_day,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
      base_patients AS bp
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON bp.subject_id = a.subject_id
  ),
  diagnosis_scores AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN (icd_version = 9 AND icd_code LIKE '410%') OR (icd_version = 10 AND icd_code LIKE 'I21%')
          THEN 1
          ELSE 0
        END
      ) AS has_ami,
      MAX(
        CASE
          WHEN
            (
              icd_version = 9 AND icd_code IN ('995.92', '785.52', '518.81', '518.82', '427.5')
            )
            OR (
              icd_version = 10 AND icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'J96.00', 'J80', 'I46.9')
            )
          THEN 1
          ELSE 0
        END
      ) AS has_major_complication,
      SUM(
        CASE
          WHEN
            (icd_version = 9 AND icd_code IN ('995.92', '785.52'))
            OR (icd_version = 10 AND icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9'))
          THEN 30
          WHEN
            (icd_version = 9 AND (icd_code IN ('518.81', '518.82', '427.5') OR icd_code LIKE '410%'))
            OR (icd_version = 10 AND (icd_code IN ('J96.00', 'J80', 'I46.9') OR icd_code LIKE 'I21%'))
          THEN 20
          WHEN
            (icd_version = 9 AND icd_code IN ('V58.11', '786.03'))
            OR (icd_version = 10 AND icd_code IN ('Z51.11', 'R06.03'))
          THEN 10
          ELSE 1
        END
      ) AS risk_score
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  icu_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays`
  ),
  combined_data AS (
    SELECT
      ad.hadm_id,
      ad.mortality_90_day,
      ad.los_days,
      ds.risk_score,
      ds.has_major_complication,
      CASE
        WHEN ds.has_ami = 1 AND ia.hadm_id IS NOT NULL
        THEN 'Target: AMI with ICU'
        ELSE 'Control: General Population'
      END AS cohort
    FROM
      admission_details AS ad
    INNER JOIN
      diagnosis_scores AS ds ON ad.hadm_id = ds.hadm_id
    LEFT JOIN
      icu_admissions AS ia ON ad.hadm_id = ia.hadm_id
    WHERE
      ds.risk_score IS NOT NULL
  ),
  target_median_risk AS (
    SELECT
      APPROX_QUANTILES(risk_score, 2)[OFFSET(1)] AS median_risk_score
    FROM
      combined_data
    WHERE
      cohort = 'Target: AMI with ICU'
  )
SELECT
  cohort,
  COUNT(hadm_id) AS patient_admission_count,
  APPROX_QUANTILES(risk_score, 100)[OFFSET(50)] AS median_risk_score,
  (
    APPROX_QUANTILES(risk_score, 100)[OFFSET(75)] - APPROX_QUANTILES(risk_score, 100)[OFFSET(25)]
  ) AS iqr_risk_score,
  AVG(mortality_90_day) * 100 AS mortality_90_day_rate_pct,
  AVG(has_major_complication) * 100 AS major_complication_rate_pct,
  APPROX_QUANTILES(
    CASE WHEN mortality_90_day = 0 THEN los_days END, 100
  )[OFFSET(50)] AS median_survivor_los_days,
  CASE
    WHEN cohort = 'Control: General Population'
    THEN (
      SELECT
        COUNTIF(cd.risk_score < tmr.median_risk_score) * 100.0 / COUNT(cd.risk_score)
      FROM
        combined_data AS cd,
        target_median_risk AS tmr
      WHERE
        cd.cohort = 'Control: General Population'
    )
    ELSE NULL
  END AS target_median_risk_percentile_in_control
FROM
  combined_data
GROUP BY
  cohort
ORDER BY
  cohort DESC;
