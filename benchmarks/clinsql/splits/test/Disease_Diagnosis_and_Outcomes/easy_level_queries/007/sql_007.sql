WITH ugib_admissions AS (
    SELECT
        a.hadm_id,
        MAX(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)) as length_of_stay
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.admissions` a
        ON p.subject_id = a.subject_id
    JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 84 AND 94
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '578%')
            OR
            (d.icd_version = 10 AND (
                d.icd_code IN ('K92.0', 'K92.1', 'K92.2') OR
                SUBSTR(d.icd_code, 1, 4) IN (
                    'K25.0', 'K25.2', 'K25.4', 'K25.6',
                    'K26.0', 'K26.2', 'K26.4', 'K26.6',
                    'K27.0', 'K27.2', 'K27.4', 'K27.6',
                    'K28.0', 'K28.2', 'K28.4', 'K28.6'
                )
            ))
        )
    GROUP BY a.hadm_id
)
SELECT
    (APPROX_QUANTILES(length_of_stay, 4))[OFFSET(3)] - (APPROX_QUANTILES(length_of_stay, 4))[OFFSET(1)] AS iqr_length_of_stay_days
FROM ugib_admissions;
