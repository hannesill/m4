WITH dialysis_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.procedures_icd`
  WHERE
    (icd_version = 9 AND icd_code IN ('3995', '5498'))
    OR
    (icd_version = 10 AND icd_code LIKE 'Z49%')
)
SELECT
  STDDEV_SAMP(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)) AS stddev_length_of_stay
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
  `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  ON p.subject_id = a.subject_id
JOIN
  dialysis_admissions AS da
  ON a.hadm_id = da.hadm_id
WHERE
  p.gender = 'M'
  AND p.anchor_age BETWEEN 44 AND 54
  AND a.dischtime IS NOT NULL;
