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
    p.gender = 'F'
    AND p.anchor_age BETWEEN 49 AND 59
    AND d.seq_num = 1
    AND (
        (d.icd_version = 10 AND d.icd_code LIKE 'J44%')
        OR
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '491' AND '496')
    )
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
