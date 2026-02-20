WITH
  patient_cohort AS (
    SELECT DISTINCT
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes
      ON a.hadm_id = d_diabetes.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
      ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
      AND (
        d_diabetes.icd_code LIKE 'E10%'
        OR d_diabetes.icd_code LIKE 'E11%'
        OR d_diabetes.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 144
  ),
  glp1_prescriptions_in_windows AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) BETWEEN 0 AND 72
        THEN 'Early_72h'
        WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 72
        THEN 'Late_72h'
        ELSE NULL
      END AS initiation_window
    FROM
      patient_cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      (
        LOWER(rx.drug) LIKE '%semaglutide%'
        OR LOWER(rx.drug) LIKE '%liraglutide%'
        OR LOWER(rx.drug) LIKE '%dulaglutide%'
        OR LOWER(rx.drug) LIKE '%exenatide%'
        OR LOWER(rx.drug) LIKE '%lixisenatide%'
      )
      AND rx.starttime IS NOT NULL
      AND rx.starttime >= c.admittime
      AND rx.starttime <= c.dischtime
  ),
  summary_stats AS (
    SELECT
      (
        SELECT
          COUNT(DISTINCT hadm_id)
        FROM
          patient_cohort
      ) AS total_cohort_admissions,
      COUNT(DISTINCT CASE WHEN initiation_window = 'Early_72h' THEN hadm_id END) AS early_window_admissions,
      COUNT(DISTINCT CASE WHEN initiation_window = 'Late_72h' THEN hadm_id END) AS late_window_admissions
    FROM
      glp1_prescriptions_in_windows
  )
SELECT
  s.total_cohort_admissions,
  s.early_window_admissions,
  s.late_window_admissions,
  ROUND(SAFE_DIVIDE(s.early_window_admissions, s.total_cohort_admissions) * 100, 2) AS early_initiation_rate_pct,
  ROUND(SAFE_DIVIDE(s.late_window_admissions, s.total_cohort_admissions) * 100, 2) AS late_initiation_rate_pct,
  ROUND(
    (SAFE_DIVIDE(s.late_window_admissions, s.total_cohort_admissions) * 100) - (SAFE_DIVIDE(s.early_window_admissions, s.total_cohort_admissions) * 100),
    2
  ) AS absolute_change_in_rate_pct,
  ROUND(
    SAFE_DIVIDE(
      CAST(s.late_window_admissions AS FLOAT64) - s.early_window_admissions,
      s.early_window_admissions
    ) * 100,
    2
  ) AS relative_change_in_rate_pct
FROM
  summary_stats AS s;
