WITH
  cohort_admissions AS (
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
      AND (
        d_diabetes.icd_code LIKE 'E11%'
        OR d_diabetes.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
  ),
  regimen_flags_per_admission AS (
    SELECT
      c.hadm_id,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) BETWEEN 0 AND 72
          AND LOWER(rx.drug) LIKE ANY ('%glargine%', '%detemir%', '%lantus%', '%levemir%', '%nph%')
          THEN 1
          ELSE 0
        END
      ) AS adm_has_basal,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) BETWEEN 0 AND 72
          AND LOWER(rx.drug) LIKE ANY ('%lispro%', '%aspart%', '%glulisine%', '%humalog%', '%novolog%', '%apidra%', '%regular%')
          THEN 1
          ELSE 0
        END
      ) AS adm_has_bolus,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) BETWEEN 0 AND 72
          AND LOWER(rx.drug) LIKE ANY ('%sliding scale%', '%ssi%')
          THEN 1
          ELSE 0
        END
      ) AS adm_has_sliding_scale,
      MAX(
        CASE
          WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48
          AND LOWER(rx.drug) LIKE ANY ('%glargine%', '%detemir%', '%lantus%', '%levemir%', '%nph%')
          THEN 1
          ELSE 0
        END
      ) AS dsch_has_basal,
      MAX(
        CASE
          WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48
          AND LOWER(rx.drug) LIKE ANY ('%lispro%', '%aspart%', '%glulisine%', '%humalog%', '%novolog%', '%apidra%', '%regular%')
          THEN 1
          ELSE 0
        END
      ) AS dsch_has_bolus,
      MAX(
        CASE
          WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48
          AND LOWER(rx.drug) LIKE ANY ('%sliding scale%', '%ssi%')
          THEN 1
          ELSE 0
        END
      ) AS dsch_has_sliding_scale
    FROM
      cohort_admissions AS c
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
      AND LOWER(rx.drug) LIKE '%insulin%'
      AND rx.starttime IS NOT NULL
    GROUP BY
      c.hadm_id
  ),
  regimen_counts AS (
    SELECT
      'Basal' AS regimen_type,
      COUNTIF(adm_has_basal = 1) AS admission_window_count,
      COUNTIF(dsch_has_basal = 1) AS discharge_window_count
    FROM regimen_flags_per_admission
    UNION ALL
    SELECT
      'Bolus' AS regimen_type,
      COUNTIF(adm_has_bolus = 1) AS admission_window_count,
      COUNTIF(dsch_has_bolus = 1) AS discharge_window_count
    FROM regimen_flags_per_admission
    UNION ALL
    SELECT
      'Basal-Bolus' AS regimen_type,
      COUNTIF(adm_has_basal = 1 AND adm_has_bolus = 1) AS admission_window_count,
      COUNTIF(dsch_has_basal = 1 AND dsch_has_bolus = 1) AS discharge_window_count
    FROM regimen_flags_per_admission
    UNION ALL
    SELECT
      'Sliding-Scale' AS regimen_type,
      COUNTIF(adm_has_sliding_scale = 1) AS admission_window_count,
      COUNTIF(dsch_has_sliding_scale = 1) AS discharge_window_count
    FROM regimen_flags_per_admission
  )
SELECT
  rc.regimen_type,
  (SELECT COUNT(*) FROM cohort_admissions) AS total_cohort_admissions,
  rc.admission_window_count,
  rc.discharge_window_count,
  ROUND(rc.admission_window_count * 100.0 / (SELECT COUNT(*) FROM cohort_admissions), 2) AS admission_initiation_pct,
  ROUND(rc.discharge_window_count * 100.0 / (SELECT COUNT(*) FROM cohort_admissions), 2) AS discharge_initiation_pct,
  ROUND(
    (rc.admission_window_count * 100.0 / (SELECT COUNT(*) FROM cohort_admissions)) -
    (rc.discharge_window_count * 100.0 / (SELECT COUNT(*) FROM cohort_admissions)),
    2
  ) AS absolute_difference_pct_points
FROM
  regimen_counts AS rc
ORDER BY
  CASE
    WHEN regimen_type = 'Basal-Bolus' THEN 1
    WHEN regimen_type = 'Basal' THEN 2
    WHEN regimen_type = 'Bolus' THEN 3
    WHEN regimen_type = 'Sliding-Scale' THEN 4
  END;
