WITH hhs_admissions AS (
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
        p.gender = 'M'
        AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 58 AND 68
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '2502%')
            OR (d.icd_version = 10 AND (d.icd_code LIKE 'E110%' OR d.icd_code LIKE 'E130%'))
        )
),
imaging_counts AS (
    SELECT
        h.subject_id,
        h.hadm_id,
        h.length_of_stay,
        COUNT(pr.icd_code) AS imaging_procedure_count
    FROM
        hhs_admissions AS h
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON h.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '87%')
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    GROUP BY
        h.subject_id, h.hadm_id, h.length_of_stay
)
SELECT
    CASE
        WHEN ic.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
        WHEN ic.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day Stay'
    END AS los_group,
    COUNT(DISTINCT ic.subject_id) AS patient_count,
    COUNT(ic.hadm_id) AS admission_count,
    ROUND(AVG(ic.imaging_procedure_count), 2) AS avg_imaging_procedures_per_admission,
    MIN(ic.imaging_procedure_count) AS min_imaging_procedures,
    MAX(ic.imaging_procedure_count) AS max_imaging_procedures
FROM
    imaging_counts AS ic
WHERE
    ic.length_of_stay BETWEEN 1 AND 7
GROUP BY
    los_group
ORDER BY
    los_group;
