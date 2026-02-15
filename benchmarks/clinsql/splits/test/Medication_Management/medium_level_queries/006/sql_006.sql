WITH
  patient_cohort AS (
    SELECT DISTINCT
      adm.hadm_id,
      adm.admittime,
      adm.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx_diabetes
      ON adm.hadm_id = dx_diabetes.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx_hf
      ON adm.hadm_id = dx_hf.hadm_id
    WHERE
      pat.gender = 'F'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 48 AND 58
      AND (
        dx_diabetes.icd_code LIKE 'E11%'
        OR (dx_diabetes.icd_version = 9 AND dx_diabetes.icd_code LIKE '250%' AND SUBSTR(dx_diabetes.icd_code, 5, 1) NOT IN ('1', '3'))
      )
      AND (
        dx_hf.icd_code LIKE 'I50%'
        OR dx_hf.icd_code LIKE '428%'
      )
      AND adm.dischtime IS NOT NULL
      AND adm.admittime IS NOT NULL
      AND DATETIME_DIFF(adm.dischtime, adm.admittime, HOUR) >= 72
  ),
  glp1_timed_prescriptions AS (
    SELECT
      cohort.hadm_id,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 72
            THEN 1
          ELSE 0
        END
      ) AS initiated_in_first_72h,
      MAX(
        CASE
          WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48
            THEN 1
          ELSE 0
        END
      ) AS initiated_in_last_48h
    FROM
      patient_cohort AS cohort
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON cohort.hadm_id = rx.hadm_id
    WHERE
      (
        LOWER(rx.drug) LIKE '%liraglutide%'
        OR LOWER(rx.drug) LIKE '%semaglutide%'
        OR LOWER(rx.drug) LIKE '%dulaglutide%'
        OR LOWER(rx.drug) LIKE '%exenatide%'
        OR LOWER(rx.drug) LIKE '%victoza%'
        OR LOWER(rx.drug) LIKE '%ozempic%'
        OR LOWER(rx.drug) LIKE '%trulicity%'
        OR LOWER(rx.drug) LIKE '%byetta%'
      )
      AND LOWER(rx.route) = 'sc'
      AND rx.starttime IS NOT NULL
      AND rx.starttime >= cohort.admittime AND rx.starttime <= cohort.dischtime
    GROUP BY
      cohort.hadm_id
  )
SELECT
  COUNT(cohort.hadm_id) AS total_admissions_in_cohort,
  SUM(COALESCE(glp1.initiated_in_first_72h, 0)) AS admissions_with_glp1_in_first_72h,
  SUM(COALESCE(glp1.initiated_in_last_48h, 0)) AS admissions_with_glp1_in_last_48h,
  ROUND(
    SAFE_DIVIDE(SUM(COALESCE(glp1.initiated_in_first_72h, 0)) * 100.0, COUNT(cohort.hadm_id)),
    2
  ) AS prevalence_first_72h_pct,
  ROUND(
    SAFE_DIVIDE(SUM(COALESCE(glp1.initiated_in_last_48h, 0)) * 100.0, COUNT(cohort.hadm_id)),
    2
  ) AS prevalence_last_48h_pct,
  (
    ROUND(
      SAFE_DIVIDE(SUM(COALESCE(glp1.initiated_in_last_48h, 0)) * 100.0, COUNT(cohort.hadm_id)),
      2
    ) -
    ROUND(
      SAFE_DIVIDE(SUM(COALESCE(glp1.initiated_in_first_72h, 0)) * 100.0, COUNT(cohort.hadm_id)),
      2
    )
  ) AS absolute_difference_pp
FROM
  patient_cohort AS cohort
LEFT JOIN
  glp1_timed_prescriptions AS glp1
  ON cohort.hadm_id = glp1.hadm_id;
