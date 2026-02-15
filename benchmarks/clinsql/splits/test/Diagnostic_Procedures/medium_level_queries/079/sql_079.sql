WITH lgib_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        MIN(d.seq_num) AS min_lgib_seq_num
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 71 AND 81
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code IN ('5781', '5693'))
            OR (d.icd_version = 10 AND d.icd_code IN ('K921', 'K922', 'K625'))
        )
    GROUP BY
        a.hadm_id, a.subject_id, length_of_stay
),
imaging_counts AS (
    SELECT
        la.hadm_id,
        la.length_of_stay,
        CASE
            WHEN la.min_lgib_seq_num = 1 THEN 'Primary Diagnosis'
            ELSE 'Secondary Diagnosis'
        END AS diagnosis_priority,
        COUNT(pr.icd_code) AS imaging_procedure_count
    FROM
        lgib_admissions AS la
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON la.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%'))
            OR (pr.icd_version = 10 AND SUBSTR(pr.icd_code, 1, 1) = 'B' AND SUBSTR(pr.icd_code, 3, 1) IN ('0', '2'))
        )
    GROUP BY
        la.hadm_id, la.length_of_stay, diagnosis_priority
)
SELECT
    CASE
        WHEN ic.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Days'
        WHEN ic.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Days'
    END AS stay_category,
    ic.diagnosis_priority,
    COUNT(DISTINCT ic.hadm_id) AS num_admissions,
    ROUND(AVG(ic.imaging_procedure_count), 2) AS avg_imaging_procedures,
    MIN(ic.imaging_procedure_count) AS min_imaging_procedures,
    MAX(ic.imaging_procedure_count) AS max_imaging_procedures
FROM
    imaging_counts AS ic
WHERE
    ic.length_of_stay BETWEEN 1 AND 7
GROUP BY
    stay_category,
    ic.diagnosis_priority
ORDER BY
    ic.diagnosis_priority,
    stay_category;
