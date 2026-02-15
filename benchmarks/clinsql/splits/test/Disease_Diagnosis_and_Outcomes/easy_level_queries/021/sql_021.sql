WITH
  AdmissionsWithBothDiagnoses AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
    HAVING
      COUNTIF(
        (icd_version = 9 AND (icd_code LIKE '430%' OR icd_code LIKE '431%' OR icd_code LIKE '432%')) OR
        (icd_version = 10 AND (icd_code LIKE 'I60%' OR icd_code LIKE 'I61%' OR icd_code LIKE 'I62%'))
      ) > 0
      AND
      COUNTIF(
        (icd_version = 9 AND icd_code = '49121') OR
        (icd_version = 10 AND icd_code = 'J441')
      ) > 0
  )
SELECT
  (
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 4) [OFFSET(3)]
  ) - (
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 4) [OFFSET(1)]
  ) AS iqr_length_of_stay_days
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
  `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  ON p.subject_id = a.subject_id
JOIN
  AdmissionsWithBothDiagnoses AS d
  ON a.hadm_id = d.hadm_id
WHERE
  p.gender = 'F'
  AND p.anchor_age BETWEEN 58 AND 68
  AND a.dischtime IS NOT NULL
  AND a.admittime IS NOT NULL
  AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
