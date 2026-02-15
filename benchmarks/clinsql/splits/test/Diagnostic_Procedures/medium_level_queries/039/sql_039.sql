WITH asthma_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
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
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '493__1' OR d.icd_code LIKE '493__2'))
            OR (d.icd_version = 10 AND d.icd_code LIKE 'J45%1')
        )
),
imaging_counts AS (
    SELECT
        aa.hadm_id,
        aa.length_of_stay,
        aa.icu_status,
        COUNT(pr.icd_code) AS imaging_procedure_count
    FROM
        asthma_admissions AS aa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON aa.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88.9%'))
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%' AND SUBSTR(pr.icd_code, 4, 1) IN ('0', '1', '2', '3'))
        )
    GROUP BY
        aa.hadm_id, aa.length_of_stay, aa.icu_status
)
SELECT
    CASE
        WHEN ic.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
        WHEN ic.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
    END AS los_category,
    ic.icu_status,
    COUNT(ic.hadm_id) AS number_of_admissions,
    ROUND(AVG(ic.imaging_procedure_count), 2) AS mean_imaging_procedures,
    MIN(ic.imaging_procedure_count) AS min_imaging_procedures,
    MAX(ic.imaging_procedure_count) AS max_imaging_procedures
FROM
    imaging_counts AS ic
GROUP BY
    los_category, ic.icu_status
ORDER BY
    los_category, ic.icu_status;
