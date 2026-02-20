SELECT
    ROUND(AVG(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)), 2) as avg_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 78 AND 88
    AND d.seq_num = 1
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
    AND (
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '410' AND '414')
        OR
        (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'I20' AND 'I25')
    );
