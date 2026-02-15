WITH
  patient_cohort AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
    WHERE
      pat.gender = 'F'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 69 AND 79
      AND adm.dischtime IS NOT NULL AND adm.admittime IS NOT NULL
      AND DATETIME_DIFF(adm.dischtime, adm.admittime, HOUR) >= 72
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE dx.hadm_id = adm.hadm_id
          AND (dx.icd_code LIKE 'E11%' OR dx.icd_code LIKE '250__0' OR dx.icd_code LIKE '250__2')
      )
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE dx.hadm_id = adm.hadm_id
          AND (dx.icd_code LIKE 'I50%' OR dx.icd_code LIKE '428%')
      )
  ),
  total_cohort_size AS (
    SELECT COUNT(DISTINCT hadm_id) AS total_patients
    FROM patient_cohort
  ),
  medication_classes AS (
    SELECT 'Insulin' AS medication_class UNION ALL
    SELECT 'Metformin' UNION ALL
    SELECT 'Sulfonylurea' UNION ALL
    SELECT 'DPP-4 Inhibitor' UNION ALL
    SELECT 'SGLT2 Inhibitor' UNION ALL
    SELECT 'GLP-1 Agonist' UNION ALL
    SELECT 'Thiazolidinedione'
  ),
  patient_medication_exposure AS (
    SELECT
      pc.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
        WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Metformin'
        WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' THEN 'Sulfonylurea'
        WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' THEN 'DPP-4 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%canagliflozin%' OR LOWER(rx.drug) LIKE '%dapagliflozin%' OR LOWER(rx.drug) LIKE '%empagliflozin%' THEN 'SGLT2 Inhibitor'
        WHEN LOWER(rx.drug) LIKE '%liraglutide%' OR LOWER(rx.drug) LIKE '%semaglutide%' OR LOWER(rx.drug) LIKE '%exenatide%' OR LOWER(rx.drug) LIKE '%dulaglutide%' THEN 'GLP-1 Agonist'
        WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%' THEN 'Thiazolidinedione'
        ELSE NULL
      END AS medication_class,
      (DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 72) AS in_first_72h,
      (DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 72) AS in_last_72h
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON pc.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime >= pc.admittime AND rx.starttime <= pc.dischtime
  ),
  patient_level_summary AS (
    SELECT
      hadm_id,
      medication_class,
      LOGICAL_OR(in_first_72h) AS received_in_first_72h,
      LOGICAL_OR(in_last_72h) AS received_in_last_72h
    FROM patient_medication_exposure
    WHERE medication_class IS NOT NULL
    GROUP BY
      hadm_id,
      medication_class
  )
SELECT
  mc.medication_class,
  ROUND(
    COUNT(DISTINCT CASE WHEN pls.received_in_first_72h THEN pls.hadm_id END) * 100.0 /
    (SELECT total_patients FROM total_cohort_size), 2
  ) AS prevalence_first_72h_pct,
  ROUND(
    COUNT(DISTINCT CASE WHEN pls.received_in_last_72h THEN pls.hadm_id END) * 100.0 /
    (SELECT total_patients FROM total_cohort_size), 2
  ) AS prevalence_last_72h_pct
FROM
  medication_classes AS mc
LEFT JOIN
  patient_level_summary AS pls ON mc.medication_class = pls.medication_class
GROUP BY
  mc.medication_class
ORDER BY
  CASE mc.medication_class
    WHEN 'Insulin' THEN 1
    WHEN 'Metformin' THEN 2
    WHEN 'Sulfonylurea' THEN 3
    WHEN 'DPP-4 Inhibitor' THEN 4
    WHEN 'SGLT2 Inhibitor' THEN 5
    WHEN 'GLP-1 Agonist' THEN 6
    WHEN 'Thiazolidinedione' THEN 7
  END;
