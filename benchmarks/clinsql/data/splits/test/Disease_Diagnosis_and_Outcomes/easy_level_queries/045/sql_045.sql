WITH hadm_with_conditions AS (
  SELECT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  GROUP BY
    hadm_id
  HAVING
    SUM(CASE
      WHEN (icd_version = 10 AND icd_code LIKE 'I50%')
        OR (icd_version = 9 AND icd_code LIKE '428%')
      THEN 1
      ELSE 0
    END) > 0
    AND
    SUM(CASE
      WHEN (icd_version = 10 AND icd_code LIKE 'J44%')
        OR (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '491' AND '496')
      THEN 1
      ELSE 0
    END) > 0
)
SELECT
    ROUND(STDDEV_SAMP(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)), 2) as stddev_length_of_stay_days
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
  `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
JOIN
  hadm_with_conditions hwc ON a.hadm_id = hwc.hadm_id
WHERE
  p.gender = 'F'
  AND p.anchor_age BETWEEN 77 AND 87
  AND a.dischtime IS NOT NULL
  AND a.admittime IS NOT NULL
  AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
