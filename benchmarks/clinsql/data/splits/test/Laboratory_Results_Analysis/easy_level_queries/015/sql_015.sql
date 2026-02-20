WITH
  pneumonia_admissions AS (
    SELECT DISTINCT
      p.subject_id,
      adm.hadm_id,
      adm.admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON p.subject_id = adm.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON adm.hadm_id = dx.hadm_id
    WHERE
      p.gender = 'F'
      AND (
        (dx.icd_version = 9 AND SUBSTR(dx.icd_code, 1, 3) BETWEEN '480' AND '486')
        OR
        (dx.icd_version = 10 AND SUBSTR(dx.icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
      )
  ),
  avg_creatinine_first_24h AS (
    SELECT
      pa.hadm_id,
      AVG(le.valuenum) AS avg_creatinine
    FROM
      pneumonia_admissions AS pa
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON pa.hadm_id = le.hadm_id
    WHERE
      le.itemid = 50912
      AND le.charttime BETWEEN pa.admittime AND DATETIME_ADD(pa.admittime, INTERVAL 24 HOUR)
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 0.5 AND 10
    GROUP BY
      pa.hadm_id
  )
SELECT
  ROUND(MIN(ac.avg_creatinine), 2) AS min_of_24h_avg_creatinine
FROM
  avg_creatinine_first_24h AS ac;
