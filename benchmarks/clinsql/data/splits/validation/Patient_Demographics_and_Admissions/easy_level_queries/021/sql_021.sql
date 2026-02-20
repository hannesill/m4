WITH FirstPneumoniaAdmission AS (
  SELECT
    a.subject_id,
    a.hospital_expire_flag,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` dx ON a.hadm_id = dx.hadm_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.d_icd_diagnoses` d_dx ON dx.icd_code = d_dx.icd_code AND dx.icd_version = d_dx.icd_version
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 83 AND 93
    AND LOWER(d_dx.long_title) LIKE '%pneumonia%'
)
SELECT
  AVG(CAST(fpa.hospital_expire_flag AS FLOAT64)) * 100.0 AS avg_mortality_percent
FROM
  FirstPneumoniaAdmission fpa
WHERE
  fpa.admission_rank = 1;
