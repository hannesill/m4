SELECT
    ROUND(MIN(le.valuenum), 2) AS min_admission_hemoglobin
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON p.subject_id = adm.subject_id
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON adm.hadm_id = dx.hadm_id
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON adm.hadm_id = le.hadm_id
WHERE
    p.gender = 'M'
    AND
    (
        dx.icd_code LIKE '434%'
        OR dx.icd_code LIKE 'I63%'
    )
    AND le.itemid = 51222
    AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 24 HOUR)
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 7 AND 18;
