WITH
  cohort_patients AS (
    SELECT
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 42 AND 52
      AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 36
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
        WHERE d.hadm_id = a.hadm_id
          AND (
            d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%'
            OR d.icd_code LIKE '250%'
          )
      )
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
        WHERE d.hadm_id = a.hadm_id
          AND (
            d.icd_code LIKE 'I50%'
            OR d.icd_code LIKE '428%'
          )
      )
  ),
  all_med_classes AS (
    SELECT 'Insulin' AS medication_class UNION ALL
    SELECT 'Metformin' UNION ALL
    SELECT 'Sulfonylurea' UNION ALL
    SELECT 'DPP-4 Inhibitor' UNION ALL
    SELECT 'SGLT2 Inhibitor' UNION ALL
    SELECT 'GLP-1 Agonist' UNION ALL
    SELECT 'Thiazolidinedione (TZD)'
  ),
  medication_events AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Metformin'
        WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%' THEN 'Sulfonylurea'
        WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%' THEN 'DPP-4 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%canagliflozin%' OR LOWER(rx.drug) LIKE '%dapagliflozin%' OR LOWER(rx.drug) LIKE '%empagliflozin%' THEN 'SGLT2 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%exenatide%' OR LOWER(rx.drug) LIKE '%liraglutide%' OR LOWER(rx.drug) LIKE '%semaglutide%' OR LOWER(rx.drug) LIKE '%dulaglutide%' THEN 'GLP-1 Agonist'
        WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%' THEN 'Thiazolidinedione (TZD)'
        ELSE NULL
      END AS medication_class,
      CASE
        WHEN rx.starttime <= DATETIME_ADD(c.admittime, INTERVAL 24 HOUR) THEN 1
        ELSE 0
      END AS is_early_24h,
      CASE
        WHEN rx.starttime >= DATETIME_SUB(c.dischtime, INTERVAL 12 HOUR) THEN 1
        ELSE 0
      END AS is_discharge_12h
    FROM
      cohort_patients AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
  ),
  aggregated_counts AS (
    SELECT
      medication_class,
      COUNT(DISTINCT CASE WHEN is_early_24h = 1 THEN hadm_id END) AS patients_early_24h,
      COUNT(DISTINCT CASE WHEN is_discharge_12h = 1 THEN hadm_id END) AS patients_discharge_12h
    FROM
      medication_events
    WHERE
      medication_class IS NOT NULL
    GROUP BY
      medication_class
  ),
  cohort_size AS (
    SELECT COUNT(DISTINCT hadm_id) AS total_admissions
    FROM cohort_patients
  )
SELECT
  mc.medication_class,
  ROUND(
    COALESCE(agg.patients_early_24h, 0) * 100.0 / cs.total_admissions,
    2
  ) AS prevalence_early_24h_pct,
  ROUND(
    COALESCE(agg.patients_discharge_12h, 0) * 100.0 / cs.total_admissions,
    2
  ) AS prevalence_discharge_12h_pct,
  ROUND(
    (COALESCE(agg.patients_discharge_12h, 0) * 100.0 / cs.total_admissions) -
    (COALESCE(agg.patients_early_24h, 0) * 100.0 / cs.total_admissions),
    2
  ) AS net_change_pct_points,
  cs.total_admissions AS cohort_total_admissions
FROM
  all_med_classes AS mc
LEFT JOIN
  aggregated_counts AS agg
  ON mc.medication_class = agg.medication_class
CROSS JOIN
  cohort_size AS cs
ORDER BY
  prevalence_early_24h_pct DESC;
