SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 100)[OFFSET(25)] AS p25_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 74 AND 84
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
    AND d.seq_num = 1
    AND (
        (d.icd_version = 9 AND (
            d.icd_code LIKE '578%'
            OR d.icd_code LIKE '456.0%'
            OR d.icd_code LIKE '456.20%'
            OR d.icd_code LIKE '531.0%'
            OR d.icd_code LIKE '531.2%'
            OR d.icd_code LIKE '531.4%'
            OR d.icd_code LIKE '531.6%'
            OR d.icd_code LIKE '532.0%'
            OR d.icd_code LIKE '532.2%'
            OR d.icd_code LIKE '532.4%'
            OR d.icd_code LIKE '532.6%'
            OR d.icd_code LIKE '533.0%'
            OR d.icd_code LIKE '533.4%'
            OR d.icd_code LIKE '534.0%'
            OR d.icd_code LIKE '534.4%'
        ))
        OR
        (d.icd_version = 10 AND (
            d.icd_code LIKE 'K92.0%'
            OR d.icd_code LIKE 'K92.1%'
            OR d.icd_code LIKE 'K92.2%'
            OR d.icd_code LIKE 'I85.01%'
            OR d.icd_code LIKE 'K25.0%'
            OR d.icd_code LIKE 'K25.2%'
            OR d.icd_code LIKE 'K25.4%'
            OR d.icd_code LIKE 'K25.6%'
            OR d.icd_code LIKE 'K26.0%'
            OR d.icd_code LIKE 'K26.4%'
            OR d.icd_code LIKE 'K27.0%'
            OR d.icd_code LIKE 'K27.4%'
            OR d.icd_code LIKE 'K28.0%'
            OR d.icd_code LIKE 'K28.4%'
        ))
    );
