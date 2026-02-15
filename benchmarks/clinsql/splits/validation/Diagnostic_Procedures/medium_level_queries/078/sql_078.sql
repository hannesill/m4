WITH tia_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 Day Stay'
            ELSE NULL
        END AS stay_category,
        CASE WHEN icu.stay_id IS NOT NULL THEN 'ICU Stay' ELSE 'No ICU Stay' END AS icu_status
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 88 AND 98
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '435%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
        )
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
),
imaging_counts AS (
    SELECT
        tia.hadm_id,
        tia.stay_category,
        tia.icu_status,
        COUNT(proc.icd_code) AS num_imaging_procedures
    FROM
        tia_admissions AS tia
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
            ON tia.hadm_id = proc.hadm_id
            AND (
                (proc.icd_version = 9 AND (proc.icd_code LIKE '87.%' OR proc.icd_code LIKE '88.9%'))
                OR
                (proc.icd_version = 10 AND SUBSTR(proc.icd_code, 4, 1) IN ('2', '3'))
            )
    GROUP BY
        tia.hadm_id, tia.stay_category, tia.icu_status
)
SELECT
    stay_category,
    icu_status,
    COUNT(hadm_id) AS total_admissions,
    APPROX_QUANTILES(num_imaging_procedures, 100)[OFFSET(50)] AS median_imaging_procedures,
    (APPROX_QUANTILES(num_imaging_procedures, 100)[OFFSET(75)] - APPROX_QUANTILES(num_imaging_procedures, 100)[OFFSET(25)]) AS iqr_imaging_procedures,
    MIN(num_imaging_procedures) AS min_imaging_procedures,
    MAX(num_imaging_procedures) AS max_imaging_procedures
FROM
    imaging_counts
GROUP BY
    stay_category,
    icu_status
ORDER BY
    stay_category,
    icu_status;
