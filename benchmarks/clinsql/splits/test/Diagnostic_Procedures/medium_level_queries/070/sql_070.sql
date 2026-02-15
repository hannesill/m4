WITH hf_admissions AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE
            WHEN icu.stay_id IS NOT NULL THEN 'ICU Stay'
            ELSE 'No ICU Stay'
        END AS icu_status
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    LEFT JOIN
        (SELECT DISTINCT hadm_id, stay_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
        ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 59 AND 69
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '428%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
        )
    GROUP BY
        a.hadm_id, length_of_stay, icu_status
),
imaging_counts AS (
    SELECT
        hf.hadm_id,
        hf.length_of_stay,
        hf.icu_status,
        CASE
            WHEN hf.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN hf.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
        END AS stay_category,
        COUNT(proc.icd_code) AS imaging_count
    FROM
        hf_admissions AS hf
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
        ON hf.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND (proc.icd_code LIKE '87%' OR proc.icd_code LIKE '88.0%'))
            OR (proc.icd_version = 10 AND (proc.icd_code LIKE 'B0%' OR proc.icd_code LIKE 'B2%'))
        )
    WHERE
        hf.length_of_stay BETWEEN 1 AND 8
    GROUP BY
        hf.hadm_id, hf.length_of_stay, hf.icu_status
)
SELECT
    stay_category,
    icu_status,
    COUNT(hadm_id) AS num_admissions,
    APPROX_QUANTILES(imaging_count, 100)[OFFSET(25)] AS p25_imaging_count,
    APPROX_QUANTILES(imaging_count, 100)[OFFSET(50)] AS p50_imaging_count,
    APPROX_QUANTILES(imaging_count, 100)[OFFSET(75)] AS p75_imaging_count
FROM
    imaging_counts
GROUP BY
    stay_category, icu_status
ORDER BY
    stay_category, icu_status;
