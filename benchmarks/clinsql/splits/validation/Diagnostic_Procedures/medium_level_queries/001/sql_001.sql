WITH acs_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        MIN(d.seq_num) AS min_acs_seq_num
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
            OR
            (d.icd_version = 10 AND (d.icd_code LIKE 'I20.0%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%' OR d.icd_code LIKE 'I24%'))
        )
    GROUP BY
        a.hadm_id, a.subject_id, length_of_stay
),
imaging_counts AS (
    SELECT
        acs.hadm_id,
        CASE
            WHEN acs.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN acs.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
        END AS los_category,
        CASE
            WHEN acs.min_acs_seq_num = 1 THEN 'Primary Diagnosis'
            ELSE 'Secondary Diagnosis'
        END AS diagnosis_type,
        COUNT(pr.icd_code) AS imaging_procedure_count
    FROM
        acs_admissions AS acs
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON acs.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%'))
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE 'B%' AND SUBSTR(pr.icd_code, 3, 1) IN ('0', '2'))
        )
    WHERE
        acs.length_of_stay BETWEEN 1 AND 8
    GROUP BY
        acs.hadm_id, los_category, diagnosis_type
)
SELECT
    diagnosis_type,
    los_category,
    COUNT(hadm_id) AS admission_count,
    ROUND(AVG(imaging_procedure_count), 2) AS mean_imaging_procedures,
    MIN(imaging_procedure_count) AS min_imaging_procedures,
    MAX(imaging_procedure_count) AS max_imaging_procedures
FROM
    imaging_counts
GROUP BY
    diagnosis_type,
    los_category
ORDER BY
    diagnosis_type,
    los_category;
