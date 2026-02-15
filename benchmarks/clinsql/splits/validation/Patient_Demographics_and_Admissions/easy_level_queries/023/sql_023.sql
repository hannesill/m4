WITH pci_admissions AS (
  SELECT DISTINCT proc.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
    ON a.hadm_id = proc.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 68 AND 78
    AND proc.icd_version = 9
    AND proc.icd_code IN ('0066', '3606', '3607')
)
SELECT
  APPROX_QUANTILES(icu.los, 2)[OFFSET(1)] AS median_icu_los_days
FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
JOIN pci_admissions
  ON icu.hadm_id = pci_admissions.hadm_id
WHERE
  icu.los IS NOT NULL AND icu.los >= 0;
