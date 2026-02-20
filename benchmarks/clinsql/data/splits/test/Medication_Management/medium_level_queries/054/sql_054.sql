WITH
  cohort_admissions AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes
        ON a.hadm_id = d_diabetes.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
        ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 56 AND 66
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
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
  ),
  admission_med_flags AS (
    SELECT
      adm.hadm_id,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, adm.admittime, HOUR) BETWEEN 0 AND 48
            THEN 1
          ELSE 0
        END
      ) AS received_glp1_early,
      MAX(
        CASE
          WHEN DATETIME_DIFF(adm.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 24
            THEN 1
          ELSE 0
        END
      ) AS received_glp1_at_discharge
    FROM
      cohort_admissions AS adm
      LEFT JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
        ON adm.hadm_id = rx.hadm_id
        AND (
          LOWER(rx.drug) LIKE '%semaglutide%'
          OR LOWER(rx.drug) LIKE '%liraglutide%'
          OR LOWER(rx.drug) LIKE '%dulaglutide%'
          OR LOWER(rx.drug) LIKE '%exenatide%'
        )
        AND rx.starttime IS NOT NULL
        AND rx.starttime <= adm.dischtime
    GROUP BY
      adm.hadm_id
  )
SELECT
  COUNT(hadm_id) AS total_cohort_admissions,
  SUM(received_glp1_early) AS admissions_with_early_glp1,
  SUM(received_glp1_at_discharge) AS admissions_with_discharge_glp1,
  ROUND(
    SUM(received_glp1_early) * 100.0 / NULLIF(COUNT(hadm_id), 0),
    2
  ) AS early_prevalence_pct,
  ROUND(
    SUM(received_glp1_at_discharge) * 100.0 / NULLIF(COUNT(hadm_id), 0),
    2
  ) AS discharge_prevalence_pct,
  ROUND(
    (SUM(received_glp1_at_discharge) * 100.0 / NULLIF(COUNT(hadm_id), 0)) -
    (SUM(received_glp1_early) * 100.0 / NULLIF(COUNT(hadm_id), 0)),
    2
  ) AS net_change_pp
FROM
  admission_med_flags;
