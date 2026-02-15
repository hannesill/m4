WITH
  patient_cohort AS (
    SELECT DISTINCT
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes ON a.hadm_id = d_diabetes.hadm_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 83 AND 93
      AND (
        d_diabetes.icd_code LIKE 'E11%'
        OR (d_diabetes.icd_version = 9 AND d_diabetes.icd_code LIKE '250.__' AND SUBSTR(d_diabetes.icd_code, 5, 1) IN ('0', '2'))
      )
      AND (
        d_hf.icd_code LIKE 'I50%'
        OR d_hf.icd_code LIKE '428%'
      )
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
  ),
  admission_regimens AS (
    SELECT
      cohort.hadm_id,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 48
          AND (LOWER(rx.drug) LIKE '%glargine%' OR LOWER(rx.drug) LIKE '%detemir%' OR LOWER(rx.drug) LIKE '%lantus%' OR LOWER(rx.drug) LIKE '%levemir%' OR LOWER(rx.drug) LIKE '%nph%')
          THEN 1
          ELSE 0
        END
      ) AS initiated_basal_early,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 48
          AND (LOWER(rx.drug) LIKE '%lispro%' OR LOWER(rx.drug) LIKE '%aspart%' OR LOWER(rx.drug) LIKE '%regular%' OR LOWER(rx.drug) LIKE '%humalog%' OR LOWER(rx.drug) LIKE '%novolog%')
          THEN 1
          ELSE 0
        END
      ) AS initiated_bolus_early,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 48
          AND (LOWER(rx.drug) LIKE '%sliding scale%' OR LOWER(rx.drug) LIKE '%ssi%')
          THEN 1
          ELSE 0
        END
      ) AS initiated_ssi_early,
      MAX(
        CASE
          WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12
          AND (LOWER(rx.drug) LIKE '%glargine%' OR LOWER(rx.drug) LIKE '%detemir%' OR LOWER(rx.drug) LIKE '%lantus%' OR LOWER(rx.drug) LIKE '%levemir%' OR LOWER(rx.drug) LIKE '%nph%')
          THEN 1
          ELSE 0
        END
      ) AS initiated_basal_late,
      MAX(
        CASE
          WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12
          AND (LOWER(rx.drug) LIKE '%lispro%' OR LOWER(rx.drug) LIKE '%aspart%' OR LOWER(rx.drug) LIKE '%regular%' OR LOWER(rx.drug) LIKE '%humalog%' OR LOWER(rx.drug) LIKE '%novolog%')
          THEN 1
          ELSE 0
        END
      ) AS initiated_bolus_late,
      MAX(
        CASE
          WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12
          AND (LOWER(rx.drug) LIKE '%sliding scale%' OR LOWER(rx.drug) LIKE '%ssi%')
          THEN 1
          ELSE 0
        END
      ) AS initiated_ssi_late
    FROM
      patient_cohort AS cohort
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND LOWER(rx.drug) LIKE '%insulin%'
      AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
    GROUP BY
      cohort.hadm_id
  ),
  regimen_counts AS (
    SELECT
      SUM(COALESCE(ar.initiated_basal_early, 0)) AS basal_early_count,
      SUM(COALESCE(ar.initiated_bolus_early, 0)) AS bolus_early_count,
      SUM(CASE WHEN COALESCE(ar.initiated_basal_early, 0) = 1 AND COALESCE(ar.initiated_bolus_early, 0) = 1 THEN 1 ELSE 0 END) AS basal_bolus_early_count,
      SUM(COALESCE(ar.initiated_ssi_early, 0)) AS ssi_early_count,
      SUM(COALESCE(ar.initiated_basal_late, 0)) AS basal_late_count,
      SUM(COALESCE(ar.initiated_bolus_late, 0)) AS bolus_late_count,
      SUM(CASE WHEN COALESCE(ar.initiated_basal_late, 0) = 1 AND COALESCE(ar.initiated_bolus_late, 0) = 1 THEN 1 ELSE 0 END) AS basal_bolus_late_count,
      SUM(COALESCE(ar.initiated_ssi_late, 0)) AS ssi_late_count,
      COUNT(pc.hadm_id) AS total_admissions
    FROM
      patient_cohort AS pc
      LEFT JOIN admission_regimens AS ar ON pc.hadm_id = ar.hadm_id
  )
SELECT
  regimen_type,
  early_initiation_rate_pct,
  late_initiation_rate_pct,
  net_change_pp
FROM (
  SELECT
    'Total Cohort Admissions (N)' AS regimen_type,
    total_admissions AS early_initiation_rate_pct,
    total_admissions AS late_initiation_rate_pct,
    0 AS net_change_pp,
    1 AS sort_order
  FROM regimen_counts
  UNION ALL
  SELECT
    regimen_type,
    ROUND(early_count * 100.0 / total_admissions, 1) AS early_initiation_rate_pct,
    ROUND(late_count * 100.0 / total_admissions, 1) AS late_initiation_rate_pct,
    ROUND((late_count * 100.0 / total_admissions) - (early_count * 100.0 / total_admissions), 1) AS net_change_pp,
    sort_order
  FROM
    regimen_counts,
    UNNEST([
      STRUCT('Basal-Bolus' AS regimen_type, basal_bolus_early_count AS early_count, basal_bolus_late_count AS late_count, 2 AS sort_order),
      STRUCT('Basal' AS regimen_type, basal_early_count AS early_count, basal_late_count AS late_count, 3 AS sort_order),
      STRUCT('Bolus' AS regimen_type, bolus_early_count AS early_count, bolus_late_count AS late_count, 4 AS sort_order),
      STRUCT('Sliding-Scale' AS regimen_type, ssi_early_count AS early_count, ssi_late_count AS late_count, 5 AS sort_order)
    ])
)
ORDER BY
  sort_order;
