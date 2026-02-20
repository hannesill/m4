SELECT
    MAX(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)) as max_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 84 AND 94
    AND d.seq_num = 1
    AND (
        (d.icd_version = 9 AND d.icd_code LIKE '434%') OR
        (d.icd_version = 10 AND d.icd_code LIKE 'I63%')
    )
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
