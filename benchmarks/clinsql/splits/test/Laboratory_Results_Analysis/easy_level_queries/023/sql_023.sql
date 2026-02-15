WITH sepsis_admissions AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    icd_code IN ('99591', '99592', '78552')
    OR STARTS_WITH(icd_code, 'A40')
    OR STARTS_WITH(icd_code, 'A41')
    OR STARTS_WITH(icd_code, 'R65.2')
)
SELECT
  ROUND(
      (APPROX_QUANTILES(le.valuenum, 4)[OFFSET(3)] - APPROX_QUANTILES(le.valuenum, 4)[OFFSET(1)])
  , 2) AS iqr_serum_lactate
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm
  ON p.subject_id = adm.subject_id
JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le
  ON adm.hadm_id = le.hadm_id
JOIN sepsis_admissions sa
  ON adm.hadm_id = sa.hadm_id
WHERE
  p.gender = 'M'
  AND le.itemid = 50813
  AND DATE(le.charttime) = DATE(adm.dischtime)
  AND le.valuenum IS NOT NULL
  AND le.valuenum BETWEEN 0.1 AND 30;
