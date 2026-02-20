WITH
  stroke_admissions AS (
    SELECT
      a.hadm_id,
      DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 71 AND 81
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '433%' OR d.icd_code LIKE '434%'))
        OR (d.icd_version = 10 AND d.icd_code LIKE 'I63%')
      )
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
  )
SELECT
  (
    APPROX_QUANTILES(sa.length_of_stay_days, 4)[OFFSET(3)] - APPROX_QUANTILES(sa.length_of_stay_days, 4)[OFFSET(1)]
  ) AS iqr_length_of_stay_days
FROM
  stroke_admissions sa;
