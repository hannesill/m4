WITH hadm_with_both_diagnoses AS (
  SELECT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  GROUP BY
    hadm_id
  HAVING
    COUNT(CASE
      WHEN (icd_version = 9 AND icd_code LIKE '578%')
        OR (icd_version = 10 AND icd_code IN ('K920', 'K921', 'K922'))
        THEN 1
    END) > 0
    AND
    COUNT(CASE
      WHEN (icd_version = 9 AND icd_code = '49121')
        OR (icd_version = 10 AND icd_code = 'J441')
        THEN 1
    END) > 0
)
SELECT
  ROUND(AVG(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)), 2) AS avg_length_of_stay_days
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
  `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
JOIN
  hadm_with_both_diagnoses h ON a.hadm_id = h.hadm_id
WHERE
  p.gender = 'M'
  AND p.anchor_age BETWEEN 86 AND 96
  AND a.admittime IS NOT NULL
  AND a.dischtime IS NOT NULL
  AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
