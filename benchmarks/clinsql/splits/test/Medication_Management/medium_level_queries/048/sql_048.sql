WITH patient_cohort AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diab
    ON a.hadm_id = d_diab.hadm_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
    ON a.hadm_id = d_hf.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 65 AND 75
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 96
    AND (
      d_diab.icd_code LIKE '250%'
      OR d_diab.icd_code LIKE 'E08%'
      OR d_diab.icd_code LIKE 'E09%'
      OR d_diab.icd_code LIKE 'E10%'
      OR d_diab.icd_code LIKE 'E11%'
      OR d_diab.icd_code LIKE 'E13%'
    )
    AND (
      d_hf.icd_code LIKE '428%'
      OR d_hf.icd_code LIKE 'I50%'
    )
), insulin_prescriptions AS (
  SELECT
    pc.hadm_id,
    pc.admittime,
    pc.dischtime,
    pr.starttime,
    CASE
      WHEN LOWER(pr.dose_val_rx) LIKE '%sliding scale%' THEN 'Sliding_Scale'
      WHEN
        LOWER(pr.drug) LIKE '%glargine%' OR LOWER(pr.drug) LIKE '%detemir%' OR LOWER(pr.drug) LIKE '%degludec%'
        OR LOWER(pr.drug) LIKE '%lantus%' OR LOWER(pr.drug) LIKE '%levemir%' OR LOWER(pr.drug) LIKE '%toujeo%'
        OR LOWER(pr.drug) LIKE '%tresiba%' OR LOWER(pr.drug) LIKE '%nph%' OR LOWER(pr.drug) LIKE '%humulin n%'
        OR LOWER(pr.drug) LIKE '%novolin n%'
        THEN 'Basal'
      WHEN
        LOWER(pr.drug) LIKE '%lispro%' OR LOWER(pr.drug) LIKE '%aspart%' OR LOWER(pr.drug) LIKE '%glulisine%'
        OR LOWER(pr.drug) LIKE '%regular%' OR LOWER(pr.drug) LIKE '%humalog%' OR LOWER(pr.drug) LIKE '%novolog%'
        OR LOWER(pr.drug) LIKE '%apidra%' OR LOWER(pr.drug) LIKE '%humulin r%' OR LOWER(pr.drug) LIKE '%novolin r%'
        THEN 'Bolus'
      ELSE NULL
    END AS regimen_type
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
    ON pc.hadm_id = pr.hadm_id
  WHERE
    pr.starttime IS NOT NULL AND pr.starttime >= pc.admittime AND pr.starttime <= pc.dischtime
    AND LOWER(pr.drug) LIKE '%insulin%'
), regimen_by_window AS (
  SELECT
    hadm_id,
    MAX(IF(regimen_type = 'Basal' AND starttime <= DATETIME_ADD(admittime, INTERVAL 48 HOUR), 1, 0)) AS on_basal_early,
    MAX(IF(regimen_type = 'Basal' AND starttime >= DATETIME_SUB(dischtime, INTERVAL 48 HOUR), 1, 0)) AS on_basal_late,
    MAX(IF(regimen_type = 'Bolus' AND starttime <= DATETIME_ADD(admittime, INTERVAL 48 HOUR), 1, 0)) AS on_bolus_early,
    MAX(IF(regimen_type = 'Bolus' AND starttime >= DATETIME_SUB(dischtime, INTERVAL 48 HOUR), 1, 0)) AS on_bolus_late,
    MAX(IF(regimen_type = 'Sliding_Scale' AND starttime <= DATETIME_ADD(admittime, INTERVAL 48 HOUR), 1, 0)) AS on_ss_early,
    MAX(IF(regimen_type = 'Sliding_Scale' AND starttime >= DATETIME_SUB(dischtime, INTERVAL 48 HOUR), 1, 0)) AS on_ss_late
  FROM
    insulin_prescriptions
  WHERE
    regimen_type IS NOT NULL
  GROUP BY
    hadm_id, admittime, dischtime
), unpivoted_regimens AS (
  SELECT hadm_id, 'Basal' AS regimen_class, on_basal_early AS received_early, on_basal_late AS received_late FROM regimen_by_window
  UNION ALL
  SELECT hadm_id, 'Bolus' AS regimen_class, on_bolus_early AS received_early, on_bolus_late AS received_late FROM regimen_by_window
  UNION ALL
  SELECT hadm_id, 'Sliding_Scale' AS regimen_class, on_ss_early AS received_early, on_ss_late AS received_late FROM regimen_by_window
  UNION ALL
  SELECT
    hadm_id,
    'Basal-Bolus' AS regimen_class,
    IF(on_basal_early = 1 AND on_bolus_early = 1, 1, 0) AS received_early,
    IF(on_basal_late = 1 AND on_bolus_late = 1, 1, 0) AS received_late
  FROM regimen_by_window
), cohort_stats AS (
  SELECT COUNT(DISTINCT hadm_id) AS total_patients FROM patient_cohort
)
SELECT
  ur.regimen_class,
  cs.total_patients,
  SUM(ur.received_early) AS patients_on_regimen_early,
  ROUND(100.0 * SUM(ur.received_early) / cs.total_patients, 1) AS percent_on_regimen_early,
  SUM(ur.received_late) AS patients_on_regimen_late,
  ROUND(100.0 * SUM(ur.received_late) / cs.total_patients, 1) AS percent_on_regimen_late,
  SUM(IF(ur.received_early = 1 AND ur.received_late = 1, 1, 0)) AS continued_count,
  SUM(IF(ur.received_early = 0 AND ur.received_late = 1, 1, 0)) AS initiated_late_count,
  SUM(IF(ur.received_early = 1 AND ur.received_late = 0, 1, 0)) AS discontinued_count
FROM
  unpivoted_regimens AS ur,
  cohort_stats AS cs
GROUP BY
  ur.regimen_class,
  cs.total_patients
ORDER BY
  CASE
    WHEN ur.regimen_class = 'Basal' THEN 1
    WHEN ur.regimen_class = 'Bolus' THEN 2
    WHEN ur.regimen_class = 'Basal-Bolus' THEN 3
    WHEN ur.regimen_class = 'Sliding_Scale' THEN 4
    ELSE 5
  END;
