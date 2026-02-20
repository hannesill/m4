WITH dvt_admissions AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 78 AND 88
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '4534%')
            OR (d.icd_version = 10 AND (
                d.icd_code LIKE 'I801%' OR
                d.icd_code LIKE 'I802%' OR
                d.icd_code LIKE 'I803%'
            ))
        )
),

admission_details AS (
    SELECT
        da.subject_id,
        da.hadm_id,
        da.length_of_stay,
        MAX(CASE WHEN icu.stay_id IS NOT NULL THEN 1 ELSE 0 END) AS had_icu_stay_flag,
        COUNT(pr.icd_code) AS num_diagnostics
    FROM
        dvt_admissions AS da
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON da.hadm_id = icu.hadm_id
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON da.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '87%' OR
                pr.icd_code LIKE '88%' OR
                pr.icd_code LIKE '89.5%'
            ))
            OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE 'B%' OR
                pr.icd_code LIKE '4A%'
            ))
        )
    GROUP BY
        da.subject_id, da.hadm_id, da.length_of_stay
)

SELECT
    CASE
        WHEN ad.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
        WHEN ad.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
    END AS los_group,
    CASE WHEN ad.had_icu_stay_flag = 1 THEN 'ICU Stay' ELSE 'No ICU Stay' END AS icu_status,
    COUNT(DISTINCT ad.subject_id) AS patient_count,
    ROUND(AVG(ad.num_diagnostics), 2) AS avg_noninvasive_diagnostics,
    MIN(ad.num_diagnostics) AS min_diagnostics,
    MAX(ad.num_diagnostics) AS max_diagnostics
FROM
    admission_details AS ad
GROUP BY
    los_group, icu_status
ORDER BY
    los_group, icu_status;
