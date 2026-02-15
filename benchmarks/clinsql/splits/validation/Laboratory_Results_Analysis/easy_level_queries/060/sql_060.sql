WITH pneumonia_admissions AS (
  SELECT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND (
      SUBSTR(icd_code, 1, 3) IN ('480', '481', '482', '483', '485', '486') OR
      SUBSTR(icd_code, 1, 4) = '5070'
    )) OR
    (icd_version = 10 AND (
      SUBSTR(icd_code, 1, 3) BETWEEN 'J12' AND 'J18'
    ))
  GROUP BY hadm_id
), avg_first_day_glucose AS (
  SELECT
    le.hadm_id,
    AVG(le.valuenum) AS avg_glucose
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm ON p.subject_id = adm.subject_id
  JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le ON adm.hadm_id = le.hadm_id
  JOIN pneumonia_admissions pa ON adm.hadm_id = pa.hadm_id
  WHERE
    p.gender = 'M'
    AND le.itemid = 50931
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 50 AND 500
    AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 24 HOUR)
  GROUP BY le.hadm_id
)
SELECT
  ROUND(
    APPROX_QUANTILES(avg_glucose, 100)[OFFSET(75)],
    2
  ) AS p75_avg_glucose_first_24h
FROM avg_first_day_glucose;
