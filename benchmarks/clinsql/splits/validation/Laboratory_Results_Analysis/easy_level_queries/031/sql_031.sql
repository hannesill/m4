SELECT
    ROUND(APPROX_QUANTILES(le.valuenum, 100)[OFFSET(75)], 2) AS p75_serum_potassium
FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p ON le.subject_id = p.subject_id
WHERE
    p.gender = 'M'
    AND le.itemid = 50971
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 2.0 AND 7.0
    AND DATE(le.charttime) = DATE(adm.dischtime)
    AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
        WHERE icu.hadm_id = le.hadm_id
    );
