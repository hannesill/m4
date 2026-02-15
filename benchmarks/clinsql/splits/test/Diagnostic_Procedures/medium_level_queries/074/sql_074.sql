WITH stroke_admissions AS (
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 40 AND 50
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '434%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I63%')
        )
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
),

admission_details AS (
    SELECT
        sa.hadm_id,
        sa.length_of_stay,
        COUNT(pr.icd_code) AS imaging_procedure_count,
        MAX(CASE WHEN icu.stay_id IS NOT NULL THEN 1 ELSE 0 END) AS had_icu_stay
    FROM
        stroke_admissions AS sa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON sa.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '87%')
            OR (pr.icd_version = 9 AND pr.icd_code LIKE '88%')
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON sa.hadm_id = icu.hadm_id
    GROUP BY
        sa.hadm_id, sa.length_of_stay
)

SELECT
    CASE
        WHEN ad.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
        WHEN ad.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day Stay'
    END AS stay_duration_group,
    CASE
        WHEN ad.had_icu_stay = 1 THEN 'ICU Stay'
        ELSE 'No ICU Stay'
    END AS icu_status,
    COUNT(ad.hadm_id) AS number_of_admissions,
    ROUND(AVG(ad.imaging_procedure_count), 2) AS avg_imaging_procedures,
    MIN(ad.imaging_procedure_count) AS min_imaging_procedures,
    MAX(ad.imaging_procedure_count) AS max_imaging_procedures
FROM
    admission_details AS ad
GROUP BY
    stay_duration_group, icu_status
ORDER BY
    stay_duration_group, icu_status DESC;
