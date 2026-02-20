SELECT
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 2)[OFFSET(1)] AS median_length_of_stay_days
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 69 AND 79
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
    AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_ugib
        WHERE d_ugib.hadm_id = a.hadm_id
        AND (
            (d_ugib.icd_version = 9 AND d_ugib.icd_code LIKE '578%') OR
            (d_ugib.icd_version = 10 AND d_ugib.icd_code IN (
                'K920',
                'K921',
                'K922',
                'K2901'
            ))
        )
    )
    AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_copd
        WHERE d_copd.hadm_id = a.hadm_id
        AND (
            (d_copd.icd_version = 9 AND d_copd.icd_code = '49121') OR
            (d_copd.icd_version = 10 AND d_copd.icd_code = 'J441')
        )
    );
