WITH
  pe_admissions AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 10 AND icd_code LIKE 'I26%')
      OR (icd_version = 9 AND icd_code LIKE '415.1%')
    GROUP BY
      hadm_id
  ),
  cohort_base AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) AS age_at_admission,
      adm.admittime,
      adm.dischtime,
      COALESCE(adm.deathtime, pat.dod) AS deathtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON pat.subject_id = adm.subject_id
    INNER JOIN
      pe_admissions AS pe ON adm.hadm_id = pe.hadm_id
    WHERE
      pat.gender = 'F'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 70 AND 80
  ),
  diagnoses_flags AS (
    SELECT
      dx.hadm_id,
      MAX(IF((dx.icd_version = 10 AND dx.icd_code IN ('R65.21', 'A41.9')) OR (dx.icd_version = 9 AND dx.icd_code IN ('995.92', '038.9')), 1, 0)) AS has_sepsis,
      MAX(IF((dx.icd_version = 10 AND dx.icd_code LIKE 'I21%') OR (dx.icd_version = 9 AND dx.icd_code LIKE '410%'), 1, 0)) AS has_mi,
      MAX(IF((dx.icd_version = 10 AND dx.icd_code LIKE 'N18%') OR (dx.icd_version = 9 AND dx.icd_code LIKE '585%'), 1, 0)) AS has_ckd,
      MAX(IF((dx.icd_version = 10 AND STARTS_WITH(dx.icd_code, 'C')) OR (dx.icd_version = 9 AND dx.icd_code BETWEEN '140' AND '209'), 1, 0)) AS has_cancer,
      MAX(IF((dx.icd_version = 10 AND dx.icd_code LIKE 'N17%') OR (dx.icd_version = 9 AND dx.icd_code LIKE '584%'), 1, 0)) AS has_aki,
      MAX(IF((dx.icd_version = 10 AND dx.icd_code = 'J80') OR (dx.icd_version = 9 AND dx.icd_code IN ('518.82', '518.5')), 1, 0)) AS has_ards
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    WHERE
      dx.hadm_id IN (SELECT hadm_id FROM cohort_base)
    GROUP BY
      dx.hadm_id
  ),
  cohort_features AS (
    SELECT
      cb.hadm_id,
      DATETIME_DIFF(cb.dischtime, cb.admittime, DAY) AS los_days,
      (cb.deathtime IS NOT NULL AND DATETIME_DIFF(cb.deathtime, cb.admittime, DAY) <= 90) AS is_dead_at_90_days,
      COALESCE(df.has_aki, 0) AS has_aki,
      COALESCE(df.has_ards, 0) AS has_ards,
      (
        (cb.age_at_admission - 70) * 2
        + (COALESCE(df.has_sepsis, 0) * 25)
        + (COALESCE(df.has_cancer, 0) * 20)
        + (COALESCE(df.has_mi, 0) * 15)
        + (COALESCE(df.has_ckd, 0) * 10)
      ) AS risk_score
    FROM
      cohort_base AS cb
    LEFT JOIN
      diagnoses_flags AS df ON cb.hadm_id = df.hadm_id
  ),
  risk_stratification AS (
    SELECT
      *,
      NTILE(5) OVER (ORDER BY risk_score) AS risk_quintile
    FROM
      cohort_features
  ),
  general_pop_mortality AS (
    SELECT
      SAFE_DIVIDE(
        COUNTIF(cb.deathtime IS NOT NULL AND DATETIME_DIFF(cb.deathtime, cb.admittime, DAY) <= 90),
        COUNT(cb.hadm_id)
      ) AS general_pop_90d_mortality_rate
    FROM (
      SELECT
        adm.hadm_id,
        adm.admittime,
        COALESCE(adm.deathtime, pat.dod) AS deathtime
      FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON pat.subject_id = adm.subject_id
      WHERE
        pat.gender = 'F'
        AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 70 AND 80
    ) AS cb
  )
SELECT
  rs.risk_quintile,
  COUNT(rs.hadm_id) AS total_patients,
  MIN(rs.risk_score) AS min_risk_score,
  MAX(rs.risk_score) AS max_risk_score,
  SAFE_DIVIDE(SUM(IF(rs.is_dead_at_90_days, 1, 0)), COUNT(rs.hadm_id)) AS pe_cohort_90d_mortality_rate,
  gpm.general_pop_90d_mortality_rate,
  AVG(rs.has_aki) AS aki_rate,
  AVG(rs.has_ards) AS ards_rate,
  APPROX_QUANTILES(
    IF(NOT rs.is_dead_at_90_days, rs.los_days, NULL), 100 IGNORE NULLS
  )[OFFSET(50)] AS median_survivor_los_days
FROM
  risk_stratification AS rs
CROSS JOIN
  general_pop_mortality AS gpm
GROUP BY
  rs.risk_quintile,
  gpm.general_pop_90d_mortality_rate
ORDER BY
  rs.risk_quintile;
