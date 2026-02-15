WITH
  pancreatitis_admissions AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 35 AND 45
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '577.0%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
      )
  ),
  admission_features AS (
    SELECT
      pa.hadm_id,
      pa.subject_id,
      pa.admittime,
      pa.dischtime,
      pa.hospital_expire_flag,
      COUNT(DISTINCT diag.icd_code) AS total_diagnoses_count,
      MAX(
        CASE
          WHEN (diag.icd_version = 10 AND diag.icd_code IN ('R68.81', 'R57.0'))
            OR (diag.icd_version = 9 AND diag.icd_code IN ('995.92', '785.52'))
          THEN 1 ELSE 0
        END
      ) AS has_multi_organ_failure,
      MAX(
        CASE
          WHEN (diag.icd_version = 10 AND diag.icd_code IN ('R65.21', 'A41.9'))
            OR (diag.icd_version = 9 AND diag.icd_code IN ('995.92', '038.9'))
          THEN 1 ELSE 0
        END
      ) AS has_septic_shock,
      MAX(
        CASE
          WHEN (diag.icd_version = 10 AND (diag.icd_code LIKE 'I21%' OR diag.icd_code = 'I46.9'))
            OR (diag.icd_version = 9 AND (diag.icd_code LIKE '410%' OR diag.icd_code = '427.5'))
          THEN 1 ELSE 0
        END
      ) AS has_acute_mi_complication,
      MAX(
        CASE
          WHEN (diag.icd_version = 10 AND diag.icd_code IN ('J96.00', 'J80'))
            OR (diag.icd_version = 9 AND diag.icd_code IN ('518.81', '518.82'))
          THEN 1 ELSE 0
        END
      ) AS has_respiratory_failure
    FROM
      pancreatitis_admissions AS pa
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag
      ON pa.hadm_id = diag.hadm_id
    GROUP BY
      pa.hadm_id,
      pa.subject_id,
      pa.admittime,
      pa.dischtime,
      pa.hospital_expire_flag
  ),
  risk_scores_and_strata AS (
    SELECT
      hadm_id,
      hospital_expire_flag,
      DATETIME_DIFF(dischtime, admittime, DAY) AS los_days,
      (
        total_diagnoses_count + 5 * (
          has_multi_organ_failure + has_septic_shock + has_acute_mi_complication + has_respiratory_failure
        )
      ) AS composite_risk_score,
      GREATEST(
        has_multi_organ_failure, has_septic_shock, has_acute_mi_complication, has_respiratory_failure
      ) AS has_major_complication,
      NTILE(4) OVER (
        ORDER BY
          (
            total_diagnoses_count + 5 * (
              has_multi_organ_failure + has_septic_shock + has_acute_mi_complication + has_respiratory_failure
            )
          )
      ) AS risk_quartile
    FROM
      admission_features
  )
SELECT
  CASE
    WHEN risk_quartile IS NULL THEN 'Overall Pancreatitis Cohort'
    ELSE CAST(risk_quartile AS STRING)
  END AS risk_stratum,
  COUNT(hadm_id) AS num_patients,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS in_hospital_mortality_rate_pct,
  ROUND(AVG(has_major_complication) * 100, 2) AS major_complication_rate_pct,
  APPROX_QUANTILES(IF(hospital_expire_flag = 0, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_survivor_los_days
FROM
  risk_scores_and_strata
GROUP BY
  ROLLUP(risk_quartile)
ORDER BY
  risk_quartile ASC NULLS LAST;
