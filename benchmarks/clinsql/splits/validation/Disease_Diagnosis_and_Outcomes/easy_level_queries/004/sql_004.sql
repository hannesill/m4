SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 100)[OFFSET(25)] AS p25_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 73 AND 83
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
    AND d.seq_num = 1
    AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '2501%' OR d.icd_code LIKE '2502%'))
        OR
        (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 4) IN (
            'E100', 'E101',
            'E110', 'E111',
            'E120', 'E121',
            'E130', 'E131',
            'E140', 'E141'
        ))
    );
