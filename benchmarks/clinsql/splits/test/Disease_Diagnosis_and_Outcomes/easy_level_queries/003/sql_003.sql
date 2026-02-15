SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 100)[OFFSET(25)] as p25_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 40 AND 50
    AND d.seq_num = 1
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
    AND (
        (d.icd_version = 10 AND (
            d.icd_code LIKE 'I20%' OR
            d.icd_code LIKE 'I21%' OR
            d.icd_code LIKE 'I22%' OR
            d.icd_code LIKE 'I23%' OR
            d.icd_code LIKE 'I24%' OR
            d.icd_code LIKE 'I25%'
        )) OR
        (d.icd_version = 9 AND (
            d.icd_code LIKE '410%' OR
            d.icd_code LIKE '411%' OR
            d.icd_code LIKE '412%' OR
            d.icd_code LIKE '413%' OR
            d.icd_code LIKE '414%'
        ))
    );
