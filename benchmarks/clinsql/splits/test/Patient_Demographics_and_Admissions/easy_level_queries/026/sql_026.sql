WITH cabg_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.procedures_icd`
  WHERE
    (icd_version = 9 AND icd_code LIKE '36.1%')
    OR
    (icd_version = 10 AND (
      icd_code LIKE '0210%' OR
      icd_code LIKE '0211%' OR
      icd_code LIKE '0212%'
    ))
),
ranked_patient_admissions AS (
  SELECT
    a.hospital_expire_flag,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` a
    ON p.subject_id = a.subject_id
  JOIN cabg_admissions ca
    ON a.hadm_id = ca.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 48 AND 58
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
)
SELECT
  APPROX_QUANTILES(hospital_expire_flag, 100)[OFFSET(25)] AS p25_in_hospital_mortality
FROM ranked_patient_admissions
WHERE
  admission_rank = 1;
