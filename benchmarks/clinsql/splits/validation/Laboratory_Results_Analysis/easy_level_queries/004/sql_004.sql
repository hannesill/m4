WITH
  sepsis_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code IN ('99591', '99592', '78552')
      OR icd_code IN ('A419', 'R6520', 'R6521')
  ),
  patient_level_24h_avg AS (
    SELECT
      p.subject_id,
      sa.hadm_id,
      AVG(le.valuenum) AS avg_platelet_first_24h
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON p.subject_id = adm.subject_id
      INNER JOIN sepsis_admissions AS sa ON adm.hadm_id = sa.hadm_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON adm.hadm_id = le.hadm_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 70 AND 80
      AND le.itemid = 51265
      AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 24 HOUR)
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 10 AND 1000
    GROUP BY
      p.subject_id,
      sa.hadm_id
  )
SELECT
  ROUND(APPROX_QUANTILES(pl.avg_platelet_first_24h, 100)[OFFSET(50)], 2) AS median_platelet_count_24h_avg
FROM
  patient_level_24h_avg AS pl;
