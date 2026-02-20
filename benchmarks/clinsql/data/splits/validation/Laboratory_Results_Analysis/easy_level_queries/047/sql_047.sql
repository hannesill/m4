WITH
  hf_admissions AS (
    SELECT DISTINCT
      subject_id,
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE '428%'
      OR icd_code LIKE 'I50%'
  ),
  admission_creatinine AS (
    SELECT
      le.valuenum,
      ROW_NUMBER() OVER (
        PARTITION BY
          adm.hadm_id
        ORDER BY
          le.charttime ASC
      ) AS rn
    FROM
      hf_admissions hf
      JOIN `physionet-data.mimiciv_3_1_hosp.patients` p ON hf.subject_id = p.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm ON hf.hadm_id = adm.hadm_id
      JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le ON adm.hadm_id = le.hadm_id
    WHERE
      p.gender = 'M'
      AND le.itemid = 50912
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 0.5 AND 10
      AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 24 HOUR)
  )
SELECT
  MAX(valuenum) AS max_admission_creatinine
FROM
  admission_creatinine
WHERE
  rn = 1;
