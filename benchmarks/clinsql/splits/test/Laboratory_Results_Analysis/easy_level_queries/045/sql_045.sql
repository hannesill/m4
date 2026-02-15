WITH sepsis_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code = '99591'
    OR icd_code LIKE 'A41%'
),
index_creatinine AS (
  SELECT
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le
    ON p.subject_id = le.subject_id
  JOIN sepsis_admissions sa
    ON le.hadm_id = sa.hadm_id
  WHERE
    p.gender = 'M'
    AND le.itemid = 50912
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 0.5 AND 10
)
SELECT
  ROUND(MAX(ic.valuenum), 2) as max_index_creatinine
FROM index_creatinine ic
WHERE
  ic.rn = 1;
