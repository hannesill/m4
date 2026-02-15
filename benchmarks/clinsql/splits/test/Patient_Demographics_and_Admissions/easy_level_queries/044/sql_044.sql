WITH FirstAdmissions AS (
  SELECT
    a.hospital_expire_flag,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 73 AND 83
)
SELECT
  APPROX_QUANTILES(hospital_expire_flag, 100)[OFFSET(25)] AS p25_in_hospital_mortality
FROM
  FirstAdmissions
WHERE
  admission_rank = 1;
