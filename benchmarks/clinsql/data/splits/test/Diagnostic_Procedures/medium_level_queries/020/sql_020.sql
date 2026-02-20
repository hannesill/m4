WITH tia_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE WHEN icu.hadm_id IS NOT NULL THEN 'ICU Stay' ELSE 'No ICU Stay' END AS icu_status
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 72 AND 82
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '435%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
        )
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
),
imaging_per_admission AS (
    SELECT
        tia.hadm_id,
        tia.icu_status,
        CASE
            WHEN tia.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            WHEN tia.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Day Stay'
        END AS stay_category,
        COUNT(proc.icd_code) AS imaging_procedure_count
    FROM
        tia_admissions AS tia
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
            ON tia.hadm_id = proc.hadm_id
            AND (
                (proc.icd_version = 9 AND (proc.icd_code LIKE '87%' OR proc.icd_code LIKE '88%'))
                OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
            )
    GROUP BY
        tia.hadm_id,
        tia.icu_status,
        tia.length_of_stay
)
SELECT
    stay_category,
    icu_status,
    COUNT(hadm_id) AS admission_count,
    ROUND(AVG(imaging_procedure_count), 2) AS mean_imaging_procedures
FROM
    imaging_per_admission
GROUP BY
    stay_category,
    icu_status
ORDER BY
    stay_category,
    icu_status;
