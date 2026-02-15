WITH sepsis_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code IN ('99591', '99592')
    OR STARTS_WITH(icd_code, 'A41')
    OR STARTS_WITH(icd_code, 'R652')
)
SELECT
  APPROX_QUANTILES(DATE_DIFF(DATE(icu.outtime), DATE(icu.intime), DAY), 2)[OFFSET(1)] AS median_icu_los_days
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
  `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  ON p.subject_id = icu.subject_id
JOIN
  sepsis_admissions AS s
  ON icu.hadm_id = s.hadm_id
WHERE
  p.gender = 'F'
  AND p.anchor_age BETWEEN 58 AND 68
  AND icu.outtime IS NOT NULL
  AND DATE(icu.outtime) >= DATE(icu.intime);
