WITH AdmissionGlucose AS (
  SELECT
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON p.subject_id = d.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` le ON d.hadm_id = le.hadm_id
  WHERE
    p.gender = 'F'
    AND (d.icd_code LIKE 'I63%' OR d.icd_code LIKE '434%' OR d.icd_code LIKE '433%')
    AND le.itemid = 50931
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 50 AND 500
)
SELECT
  ROUND(APPROX_QUANTILES(ag.valuenum, 100)[OFFSET(75)], 2) AS p75_admission_glucose
FROM
  AdmissionGlucose ag
WHERE
  ag.rn = 1;
