WITH
  cohort_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 67 AND 77
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 60
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id AND (
            d.icd_code LIKE 'E11%'
            OR d.icd_code LIKE '250%'
          )
      )
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id AND (
            d.icd_code LIKE 'I50%'
            OR d.icd_code LIKE '428%'
          )
      )
  ),
  classified_prescriptions AS (
    SELECT
      c.hadm_id,
      c.admittime,
      c.dischtime,
      rx.starttime,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%'
        THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%'
        THEN 'Metformin'
        WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%'
        THEN 'Sulfonylurea'
        WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%'
        THEN 'DPP-4 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%canagliflozin%' OR LOWER(rx.drug) LIKE '%dapagliflozin%' OR LOWER(rx.drug) LIKE '%empagliflozin%'
        THEN 'SGLT2 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%liraglutide%' OR LOWER(rx.drug) LIKE '%semaglutide%' OR LOWER(rx.drug) LIKE '%exenatide%' OR LOWER(rx.drug) LIKE '%dulaglutide%'
        THEN 'GLP-1 Agonist'
        WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%'
        THEN 'Thiazolidinedione'
        ELSE NULL
      END AS med_class
    FROM
      cohort_admissions AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
  ),
  medication_initiations AS (
    SELECT
      hadm_id,
      admittime,
      dischtime,
      med_class,
      MIN(starttime) AS initiation_time
    FROM
      classified_prescriptions
    WHERE
      med_class IS NOT NULL
    GROUP BY
      hadm_id,
      admittime,
      dischtime,
      med_class
  ),
  windowed_counts AS (
    SELECT
      med_class,
      COUNT(DISTINCT CASE WHEN DATETIME_DIFF(initiation_time, admittime, HOUR) <= 12 THEN hadm_id ELSE NULL END) AS early_initiation_count,
      COUNT(DISTINCT CASE WHEN DATETIME_DIFF(dischtime, initiation_time, HOUR) <= 48 THEN hadm_id ELSE NULL END) AS late_initiation_count
    FROM
      medication_initiations
    GROUP BY
      med_class
  ),
  total_cohort_size AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_admissions
    FROM
      cohort_admissions
  )
SELECT
  wc.med_class,
  ROUND(wc.early_initiation_count * 100.0 / tcs.total_admissions, 2) AS initiation_rate_first_12h_pct,
  ROUND(wc.late_initiation_count * 100.0 / tcs.total_admissions, 2) AS initiation_rate_final_48h_pct,
  ROUND((wc.late_initiation_count * 100.0 / tcs.total_admissions) - (wc.early_initiation_count * 100.0 / tcs.total_admissions), 2) AS net_change_pp
FROM
  windowed_counts AS wc
CROSS JOIN
  total_cohort_size AS tcs
ORDER BY
  net_change_pp DESC,
  wc.med_class;
