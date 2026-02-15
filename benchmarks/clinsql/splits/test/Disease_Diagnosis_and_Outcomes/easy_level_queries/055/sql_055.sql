SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 100)[OFFSET(75)] AS p75_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 37 AND 47
    AND d.seq_num = 1
    AND (
        (d.icd_version = 9 AND d.icd_code LIKE '584%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'N17%')
    )
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
