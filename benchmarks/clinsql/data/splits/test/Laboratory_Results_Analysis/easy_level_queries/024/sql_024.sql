WITH FirstPlateletCounts AS (
  SELECT
    le.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` le
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` p ON le.subject_id = p.subject_id
  INNER JOIN (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE 'A40%'
      OR icd_code LIKE 'A41%'
      OR icd_code IN ('99591', '99592', '78552')
  ) sepsis_admissions ON le.hadm_id = sepsis_admissions.hadm_id
  WHERE
    p.gender = 'M'
    AND le.itemid = 51265
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 20 AND 1000
)
SELECT
  ROUND(STDDEV(fp.valuenum), 2) AS stddev_admission_platelet_count
FROM
  FirstPlateletCounts fp
WHERE
  fp.rn = 1;
