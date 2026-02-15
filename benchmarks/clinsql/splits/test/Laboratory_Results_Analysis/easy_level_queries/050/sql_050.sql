WITH
  sepsis_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code IN ('99591', '99592', '78552')
      OR
      icd_code LIKE 'A41%'
  ),
  admission_platelet_counts AS (
    SELECT
      le.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON le.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND le.itemid = 51265
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 10 AND 1000
  )
SELECT
  ROUND(STDDEV(apc.valuenum), 2) AS stddev_admission_platelet_count
FROM
  admission_platelet_counts AS apc
  INNER JOIN sepsis_admissions AS sa ON apc.hadm_id = sa.hadm_id
WHERE
  apc.rn = 1;
