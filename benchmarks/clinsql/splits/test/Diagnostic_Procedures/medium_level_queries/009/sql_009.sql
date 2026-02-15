WITH tia_admissions AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 4 THEN '1-4 Days'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 5 AND 7 THEN '5-7 Days'
            ELSE NULL
        END AS stay_category,
        CASE
            WHEN icu.hadm_id IS NOT NULL THEN 'ICU Stay'
            ELSE 'No ICU Stay'
        END AS icu_status
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    LEFT JOIN
        (SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 44 AND 54
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '435%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
        )
),
procedure_counts AS (
    SELECT
        ta.hadm_id,
        ta.stay_category,
        ta.icu_status,
        COUNT(pr.icd_code) AS imaging_procedure_count
    FROM
        tia_admissions AS ta
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON ta.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '87%')
            OR (pr.icd_version = 9 AND pr.icd_code LIKE '88%')
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    WHERE
        ta.stay_category IS NOT NULL
    GROUP BY
        ta.hadm_id, ta.stay_category, ta.icu_status
)
SELECT
    stay_category,
    icu_status,
    COUNT(hadm_id) AS total_admissions,
    APPROX_QUANTILES(imaging_procedure_count, 100)[OFFSET(25)] AS p25_imaging_procedures,
    APPROX_QUANTILES(imaging_procedure_count, 100)[OFFSET(50)] AS p50_imaging_procedures,
    APPROX_QUANTILES(imaging_procedure_count, 100)[OFFSET(75)] AS p75_imaging_procedures
FROM
    procedure_counts
GROUP BY
    stay_category, icu_status
ORDER BY
    stay_category, icu_status;
