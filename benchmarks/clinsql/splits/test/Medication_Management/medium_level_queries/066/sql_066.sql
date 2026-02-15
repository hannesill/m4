WITH
  patient_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes ON a.hadm_id = d_diabetes.hadm_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) BETWEEN 58 AND 68
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
      AND (
        d_diabetes.icd_code LIKE 'E11%'
        OR (
          d_diabetes.icd_version = 9
          AND d_diabetes.icd_code LIKE '250.%'
        )
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
  ),
  timed_prescriptions AS (
    SELECT
      cohort.hadm_id,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 72 THEN 1
          ELSE 0
        END
      ) AS initiated_in_first_72h,
      MAX(
        CASE
          WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12 THEN 1
          ELSE 0
        END
      ) AS initiated_in_final_12h
    FROM
      patient_cohort AS cohort
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
      AND (
        LOWER(rx.drug) LIKE '%liraglutide%'
        OR LOWER(rx.drug) LIKE '%semaglutide%'
        OR LOWER(rx.drug) LIKE '%dulaglutide%'
        OR LOWER(rx.drug) LIKE '%exenatide%'
        OR LOWER(rx.drug) LIKE '%lixisenatide%'
      )
    GROUP BY
      cohort.hadm_id
  ),
  summary_stats AS (
    SELECT
      COUNT(DISTINCT cohort.hadm_id) AS total_admissions_in_cohort,
      SUM(COALESCE(tp.initiated_in_first_72h, 0)) AS count_initiated_early,
      SUM(COALESCE(tp.initiated_in_final_12h, 0)) AS count_initiated_late
    FROM
      patient_cohort AS cohort
      LEFT JOIN timed_prescriptions AS tp ON cohort.hadm_id = tp.hadm_id
  )
SELECT
  total_admissions_in_cohort,
  count_initiated_early,
  count_initiated_late,
  ROUND(
    count_initiated_early * 100.0 / NULLIF(total_admissions_in_cohort, 0),
    2
  ) AS prevalence_first_72h_pct,
  ROUND(
    count_initiated_late * 100.0 / NULLIF(total_admissions_in_cohort, 0),
    2
  ) AS prevalence_final_12h_pct,
  ROUND(
    (
      count_initiated_early * 100.0 / NULLIF(total_admissions_in_cohort, 0)
    ) - (
      count_initiated_late * 100.0 / NULLIF(total_admissions_in_cohort, 0)
    ),
    2
  ) AS absolute_difference_pp
FROM
  summary_stats;
