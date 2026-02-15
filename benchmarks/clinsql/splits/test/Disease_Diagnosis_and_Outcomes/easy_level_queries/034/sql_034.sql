WITH SepsisAdmissions AS (
  SELECT
    a.hadm_id,
    DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) as length_of_stay
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` a
    ON p.subject_id = a.subject_id
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
    ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 40 AND 50
    AND d.seq_num = 1
    AND (
      (d.icd_version = 9 AND d.icd_code IN ('99591', '99592', '78552'))
      OR
      (d.icd_version = 10 AND (d.icd_code LIKE 'A41%' OR d.icd_code LIKE 'R652%'))
    )
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
)
SELECT
  ROUND(
    (APPROX_QUANTILES(length_of_stay, 4)[OFFSET(3)]) -
    (APPROX_QUANTILES(length_of_stay, 4)[OFFSET(1)]),
  2) AS iqr_length_of_stay_days
FROM SepsisAdmissions;
