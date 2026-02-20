WITH pci_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.procedures_icd`
  WHERE icd_code IN ('0066', '3606', '3607') OR icd_code LIKE '027%'
), patient_admission_details AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    CASE WHEN pci.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS is_pci_admission,
    LEAD(a.admittime, 1) OVER (PARTITION BY p.subject_id ORDER BY a.admittime) AS next_admittime
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  LEFT JOIN pci_admissions AS pci
    ON a.hadm_id = pci.hadm_id
  WHERE p.gender = 'M'
    AND p.anchor_age BETWEEN 52 AND 62
    AND a.dischtime IS NOT NULL
), first_pci_stays AS (
  SELECT
    subject_id,
    dischtime,
    next_admittime,
    ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY admittime) AS pci_admission_num
  FROM patient_admission_details
  WHERE is_pci_admission = 1
), readmission_flags AS (
  SELECT
    subject_id,
    CASE
      WHEN next_admittime IS NOT NULL
       AND DATE_DIFF(DATE(next_admittime), DATE(dischtime), DAY) <= 30
      THEN 1
      ELSE 0
    END AS was_readmitted_within_30_days
  FROM first_pci_stays
  WHERE pci_admission_num = 1
)
SELECT
  AVG(was_readmitted_within_30_days) AS avg_30_day_readmission_rate
FROM readmission_flags;
