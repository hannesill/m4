WITH first_day_creatinine_avg AS (
    SELECT
        adm.hadm_id,
        AVG(le.valuenum) AS avg_creatinine_24h
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
        AND p.anchor_age BETWEEN 45 AND 55
        AND (
            (dx.icd_version = 9 AND SUBSTR(dx.icd_code, 1, 3) IN ('480', '481', '482', '483', '484', '485', '486'))
            OR
            (dx.icd_version = 10 AND SUBSTR(dx.icd_code, 1, 3) IN ('J12', 'J13', 'J14', 'J15', 'J16', 'J17', 'J18'))
        )
        AND le.itemid = 50912
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 0.5 AND 10
        AND le.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 24 HOUR)
    GROUP BY
        adm.hadm_id
)
SELECT
    ROUND(STDDEV(fdca.avg_creatinine_24h), 2) AS stddev_of_avg_creatinine_24h
FROM
    first_day_creatinine_avg AS fdca;
