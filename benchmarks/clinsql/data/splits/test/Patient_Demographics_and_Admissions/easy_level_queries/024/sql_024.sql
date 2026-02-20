WITH FirstAdmissions AS (
  SELECT
    subject_id,
    hadm_id,
    hospital_expire_flag,
    ROW_NUMBER() OVER(PARTITION BY subject_id ORDER BY admittime ASC) as admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions`
  WHERE
    dischtime IS NOT NULL
)
SELECT
  AVG(fa.hospital_expire_flag) AS mortality_rate
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
  FirstAdmissions AS fa
  ON p.subject_id = fa.subject_id
JOIN
  `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
  ON fa.hadm_id = proc.hadm_id
WHERE
  p.gender = 'F'
  AND p.anchor_age BETWEEN 35 AND 45
  AND fa.admission_rank = 1
  AND (proc.icd_code LIKE '361%' OR proc.icd_code LIKE '021%');
