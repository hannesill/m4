WITH
  all_female_admissions AS (
    SELECT
      p.subject_id,
      p.gender,
      p.dod,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
  ),
  cardiac_arrest_cohort AS (
    SELECT DISTINCT
      afa.subject_id,
      afa.hadm_id,
      afa.admittime,
      afa.dischtime,
      afa.dod,
      afa.hospital_expire_flag,
      afa.age_at_admission
    FROM
      all_female_admissions AS afa
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON afa.hadm_id = dx.hadm_id
    WHERE
      afa.age_at_admission BETWEEN 59 AND 69
      AND (
        (dx.icd_version = 9 AND dx.icd_code = '4275')
        OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I46%')
      )
  ),
  risk_and_complication_scores AS (
    SELECT
      dx.hadm_id,
      SUM(
        CASE
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('R68.81', 'R57.0') THEN 25
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('99592', '78552') THEN 25
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('R65.21', 'A41.9') THEN 20
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('99592', '0389') THEN 20
          WHEN dx.icd_version = 10 AND dx.icd_code IN ('J96.00', 'J80') THEN 15
          WHEN dx.icd_version = 9 AND dx.icd_code IN ('51881', '51882') THEN 15
          WHEN dx.icd_version = 10 AND dx.icd_code LIKE 'I21%' THEN 15
          WHEN dx.icd_version = 9 AND dx.icd_code LIKE '410%' THEN 15
          ELSE 0
        END
      )
      + (COUNT(DISTINCT dx.icd_code) * 0.5) AS composite_risk_score,
      MAX(
        CASE
          WHEN (dx.icd_version = 10 AND (dx.icd_code LIKE 'I21%' OR dx.icd_code IN ('R65.21', 'A41.9')))
            OR (dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code IN ('99592', '0389')))
          THEN 1
          ELSE 0
        END
      ) AS has_cardiovascular_complication,
      MAX(
        CASE
          WHEN (dx.icd_version = 10 AND dx.icd_code = 'G931')
            OR (dx.icd_version = 9 AND dx.icd_code = '3481')
          THEN 1
          ELSE 0
        END
      ) AS has_neurologic_complication
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    WHERE
      dx.hadm_id IN (SELECT hadm_id FROM cardiac_arrest_cohort)
    GROUP BY
      dx.hadm_id
  ),
  cohort_with_metrics AS (
    SELECT
      c.hadm_id,
      c.age_at_admission,
      rs.composite_risk_score,
      rs.has_cardiovascular_complication,
      rs.has_neurologic_complication,
      GREATEST(0, DATETIME_DIFF(c.dischtime, c.admittime, DAY)) AS los_days,
      CASE
        WHEN c.hospital_expire_flag = 1 THEN 1
        WHEN c.dod IS NOT NULL AND DATE_DIFF(c.dod, c.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS is_30_day_mortality,
      CASE WHEN c.hospital_expire_flag = 0 THEN 1 ELSE 0 END AS is_survivor
    FROM
      cardiac_arrest_cohort AS c
    JOIN
      risk_and_complication_scores AS rs
      ON c.hadm_id = rs.hadm_id
  ),
  ranked_cohort AS (
    SELECT
      *,
      NTILE(4) OVER (ORDER BY composite_risk_score) AS risk_quartile
    FROM
      cohort_with_metrics
  ),
  baseline_mortality AS (
    SELECT
      AVG(
        CASE
          WHEN afa.hospital_expire_flag = 1 THEN 1
          WHEN afa.dod IS NOT NULL AND DATE_DIFF(afa.dod, afa.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
          ELSE 0
        END
      ) AS baseline_mortality_rate_30_day
    FROM
      all_female_admissions AS afa
    WHERE
      afa.age_at_admission BETWEEN 59 AND 69
  )
SELECT
  r.risk_quartile,
  COUNT(r.hadm_id) AS num_patients,
  ROUND(AVG(r.composite_risk_score), 2) AS avg_risk_score,
  ROUND(MIN(r.composite_risk_score), 2) AS min_risk_score,
  ROUND(MAX(r.composite_risk_score), 2) AS max_risk_score,
  ROUND(AVG(r.is_30_day_mortality) * 100, 2) AS mortality_rate_30_day_pct,
  ROUND(AVG(r.has_cardiovascular_complication) * 100, 2) AS cardio_complication_rate_pct,
  ROUND(AVG(r.has_neurologic_complication) * 100, 2) AS neuro_complication_rate_pct,
  APPROX_QUANTILES(
    IF(r.is_survivor = 1, r.los_days, NULL), 100
  )[OFFSET(50)] AS median_survivor_los_days,
  ROUND(b.baseline_mortality_rate_30_day * 100, 2) AS baseline_all_fem_59_69_mort_pct
FROM
  ranked_cohort AS r,
  baseline_mortality AS b
GROUP BY
  r.risk_quartile,
  b.baseline_mortality_rate_30_day
ORDER BY
  r.risk_quartile;
