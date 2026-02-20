WITH acs_admissions AS (
  SELECT
    subject_id,
    hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND (
      icd_code LIKE '410%'
      OR icd_code = '4111'
    ))
    OR
    (icd_version = 10 AND (
      icd_code LIKE 'I200%'
      OR icd_code LIKE 'I21%'
      OR icd_code LIKE 'I22%'
    ))
  GROUP BY subject_id, hadm_id
)
SELECT
  ROUND(MIN(le.valuenum), 3) AS min_troponin_nadir
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN acs_admissions acs ON p.subject_id = acs.subject_id
JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le ON acs.hadm_id = le.hadm_id
WHERE
  p.gender = 'M'
  AND le.itemid IN (
    51003,
    51002
  )
  AND le.valuenum IS NOT NULL
  AND le.valuenum >= 0 AND le.valuenum < 100;
