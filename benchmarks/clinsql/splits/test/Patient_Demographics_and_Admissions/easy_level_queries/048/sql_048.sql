WITH hf_admissions AS (
  SELECT DISTINCT
    a.subject_id,
    a.admittime,
    a.dischtime
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON a.hadm_id = dx.hadm_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 79 AND 89
    AND a.dischtime IS NOT NULL
    AND (
      (dx.icd_version = 9 AND dx.icd_code LIKE '428%')
      OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I50%')
    )
), first_hf_admission_los AS (
  SELECT
    subject_id,
    DATE_DIFF(DATE(dischtime), DATE(admittime), DAY) AS los
  FROM
    (
      SELECT
        subject_id,
        admittime,
        dischtime,
        ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY admittime ASC) AS rn
      FROM
        hf_admissions
    )
  WHERE
    rn = 1
)
SELECT
  (APPROX_QUANTILES(los, 4)[OFFSET(3)] - APPROX_QUANTILES(los, 4)[OFFSET(1)]) AS iqr_length_of_stay
FROM
  first_hf_admission_los
WHERE
  los >= 0;
