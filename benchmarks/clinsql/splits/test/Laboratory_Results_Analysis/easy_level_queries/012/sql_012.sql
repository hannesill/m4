SELECT
    APPROX_QUANTILES(le.valuenum, 100)[OFFSET(75)] AS percentile_75th_platelet_count
FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p ON le.subject_id = p.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON adm.hadm_id = dx.hadm_id
WHERE
    p.gender = 'F'
    AND le.itemid = 51265
    AND DATE(le.charttime) = DATE(adm.dischtime)
    AND (
        dx.icd_code LIKE '430%' OR
        dx.icd_code LIKE '431%' OR
        dx.icd_code LIKE '432%' OR
        dx.icd_code LIKE 'I60%' OR
        dx.icd_code LIKE 'I61%' OR
        dx.icd_code LIKE 'I62%'
    )
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 10 AND 1000;
