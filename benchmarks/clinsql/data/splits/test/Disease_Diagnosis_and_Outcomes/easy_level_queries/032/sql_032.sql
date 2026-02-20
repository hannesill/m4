WITH
  admission_los AS (
    SELECT
      a.hadm_id,
      DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 81 AND 91
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
  )
SELECT
  ROUND(
    (
      APPROX_QUANTILES(los.length_of_stay_days, 4)
    ) [OFFSET(3)] - (
      APPROX_QUANTILES(los.length_of_stay_days, 4)
    ) [OFFSET(1)],
    2
  ) AS iqr_length_of_stay_days
FROM
  admission_los AS los
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON los.hadm_id = d.hadm_id
WHERE
  d.seq_num = 1
  AND (
    (
      d.icd_version = 9
      AND d.icd_code LIKE '584%'
    )
    OR (
      d.icd_version = 10
      AND d.icd_code LIKE 'N17%'
    )
  );
