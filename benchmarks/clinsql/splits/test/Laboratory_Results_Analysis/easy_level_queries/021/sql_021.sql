SELECT
    ROUND(APPROX_QUANTILES(le.valuenum, 100)[OFFSET(75)], 2) AS p75_discharge_glucose_mg_dl
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON p.subject_id = adm.subject_id
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag ON adm.hadm_id = diag.hadm_id
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON adm.hadm_id = le.hadm_id
WHERE
    p.gender = 'M'
    AND (
        (diag.icd_version = 9 AND SUBSTR(diag.icd_code, 1, 3) BETWEEN '480' AND '486')
        OR
        (diag.icd_version = 10 AND SUBSTR(diag.icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
    )
    AND le.itemid = 50931
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 50 AND 500
    AND DATE(le.charttime) = DATE(adm.dischtime);
