SELECT
  MAX(DATE_DIFF(DATE(icu.outtime), DATE(icu.intime), DAY)) AS max_icu_length_of_stay
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
  `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  ON p.subject_id = a.subject_id
JOIN
  `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  ON a.hadm_id = icu.hadm_id
JOIN
  `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
  ON a.hadm_id = proc.hadm_id
WHERE
  p.gender = 'F'
  AND p.anchor_age BETWEEN 59 AND 69
  AND (
    (proc.icd_version = 9 AND proc.icd_code IN ('0066', '3606', '3607'))
    OR
    (proc.icd_version = 10 AND STARTS_WITH(proc.icd_code, '027'))
  )
  AND icu.outtime IS NOT NULL
  AND icu.intime IS NOT NULL;
