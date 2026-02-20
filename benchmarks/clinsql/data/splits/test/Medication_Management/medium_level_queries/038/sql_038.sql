WITH
  patient_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes ON a.hadm_id = d_diabetes.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 57 AND 67
      AND (
        d_diabetes.icd_code LIKE 'E10%'
        OR d_diabetes.icd_code LIKE 'E11%'
        OR d_diabetes.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
  ),
  timed_glp1_prescriptions AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) < 72 THEN 'Early_72h'
        WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) < 24 THEN 'Discharge_24h'
        ELSE NULL
      END AS time_window,
      (
        ROW_NUMBER() OVER (
          PARTITION BY
            c.hadm_id
          ORDER BY
            rx.starttime ASC
        ) = 1
      ) AS is_first_glp1_rx
    FROM
      patient_cohort AS c
      JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND (
        LOWER(rx.drug) LIKE '%glutide%'
        OR LOWER(rx.drug) LIKE '%enatide%'
      )
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
  ),
  admission_level_summary AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN time_window = 'Early_72h' THEN 1
          ELSE 0
        END
      ) AS prescribed_in_early_window,
      MAX(
        CASE
          WHEN time_window = 'Discharge_24h' THEN 1
          ELSE 0
        END
      ) AS prescribed_in_discharge_window,
      MAX(
        CASE
          WHEN time_window = 'Early_72h' AND is_first_glp1_rx THEN 1
          ELSE 0
        END
      ) AS initiated_in_early_window,
      MAX(
        CASE
          WHEN time_window = 'Discharge_24h' AND is_first_glp1_rx THEN 1
          ELSE 0
        END
      ) AS initiated_in_discharge_window
    FROM
      timed_glp1_prescriptions
    WHERE
      time_window IS NOT NULL
    GROUP BY
      hadm_id
  ),
  final_metrics AS (
    SELECT
      (
        SELECT
          COUNT(DISTINCT hadm_id)
        FROM
          patient_cohort
      ) AS total_cohort_admissions,
      SUM(als.prescribed_in_early_window) AS prevalence_early_count,
      SUM(als.prescribed_in_discharge_window) AS prevalence_discharge_count,
      SUM(als.initiated_in_early_window) AS initiation_early_count,
      SUM(als.initiated_in_discharge_window) AS initiation_discharge_count
    FROM
      admission_level_summary AS als
  )
SELECT
  'GLP-1 Receptor Agonists' AS medication_class,
  fm.total_cohort_admissions,
  fm.prevalence_early_count,
  ROUND(
    fm.prevalence_early_count * 100.0 / fm.total_cohort_admissions,
    2
  ) AS prevalence_early_pct,
  fm.prevalence_discharge_count,
  ROUND(
    fm.prevalence_discharge_count * 100.0 / fm.total_cohort_admissions,
    2
  ) AS prevalence_discharge_pct,
  ROUND(
    (
      fm.prevalence_discharge_count * 100.0 / fm.total_cohort_admissions
    ) - (
      fm.prevalence_early_count * 100.0 / fm.total_cohort_admissions
    ),
    2
  ) AS prevalence_absolute_change_pct,
  fm.initiation_early_count,
  ROUND(
    fm.initiation_early_count * 100.0 / fm.total_cohort_admissions,
    2
  ) AS initiation_early_pct,
  fm.initiation_discharge_count,
  ROUND(
    fm.initiation_discharge_count * 100.0 / fm.total_cohort_admissions,
    2
  ) AS initiation_discharge_pct,
  ROUND(
    (
      fm.initiation_discharge_count * 100.0 / fm.total_cohort_admissions
    ) - (
      fm.initiation_early_count * 100.0 / fm.total_cohort_admissions
    ),
    2
  ) AS initiation_absolute_change_pct,
  ROUND(
    SAFE_DIVIDE(
      (
        fm.prevalence_discharge_count - fm.prevalence_early_count
      ),
      fm.prevalence_early_count
    ) * 100.0,
    1
  ) AS prevalence_relative_change_pct,
  ROUND(
    SAFE_DIVIDE(
      (
        fm.initiation_discharge_count - fm.initiation_early_count
      ),
      fm.initiation_early_count
    ) * 100.0,
    1
  ) AS initiation_relative_change_pct
FROM
  final_metrics AS fm;
