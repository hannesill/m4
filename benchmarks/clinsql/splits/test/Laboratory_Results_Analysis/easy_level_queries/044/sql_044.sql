WITH IschemicStrokeAdmissions AS (
  SELECT DISTINCT
    adm.hadm_id,
    adm.dischtime
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm
    ON p.subject_id = adm.subject_id
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` diag
    ON adm.hadm_id = diag.hadm_id
  WHERE
    p.gender = 'M'
    AND (
      (diag.icd_version = 9 AND diag.icd_code LIKE '434%')
      OR (diag.icd_version = 10 AND diag.icd_code LIKE 'I63%')
    )
),

DischargeDayGlucose AS (
  SELECT
    le.valuenum
  FROM `physionet-data.mimiciv_3_1_hosp.labevents` le
  JOIN IschemicStrokeAdmissions isa
    ON le.hadm_id = isa.hadm_id
  WHERE
    le.itemid = 50931
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 50 AND 500
    AND DATE(le.charttime) = DATE(isa.dischtime)
)
SELECT
  ROUND(
    APPROX_QUANTILES(valuenum, 4)[OFFSET(3)] - APPROX_QUANTILES(valuenum, 4)[OFFSET(1)]
  , 2) AS iqr_serum_glucose
FROM DischargeDayGlucose;
