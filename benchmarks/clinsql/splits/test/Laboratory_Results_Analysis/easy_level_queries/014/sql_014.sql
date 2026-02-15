SELECT
    ROUND(APPROX_QUANTILES(le.valuenum, 100)[OFFSET(75)], 2) AS p75_hemoglobin_at_discharge
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON p.subject_id = adm.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON adm.hadm_id = dx.hadm_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON adm.hadm_id = le.hadm_id
WHERE
    p.gender = 'F'
    AND (dx.icd_code LIKE '578%' OR dx.icd_code LIKE 'K92%')
    AND le.itemid = 51222
    AND DATE(le.charttime) = DATE(adm.dischtime)
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 7 AND 18;
