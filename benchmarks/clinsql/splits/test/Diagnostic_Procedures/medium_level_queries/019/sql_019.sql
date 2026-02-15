WITH pancreatitis_admissions AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 42 AND 52
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code = '5770')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
        )
),
admission_procedure_counts AS (
    SELECT
        pa.subject_id,
        pa.hadm_id,
        CASE
            WHEN pa.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN pa.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day Stay'
            ELSE 'Other Stay Duration'
        END AS stay_category,
        COUNT(pr.icd_code) AS diagnostic_procedure_count
    FROM
        pancreatitis_admissions AS pa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON pa.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%'))
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    GROUP BY
        pa.subject_id, pa.hadm_id, pa.length_of_stay
)
SELECT
    apc.stay_category,
    COUNT(DISTINCT apc.subject_id) AS patient_count,
    ROUND(AVG(apc.diagnostic_procedure_count), 2) AS avg_procedures_per_admission,
    MIN(apc.diagnostic_procedure_count) AS min_procedures_per_admission,
    MAX(apc.diagnostic_procedure_count) AS max_procedures_per_admission
FROM
    admission_procedure_counts AS apc
WHERE
    apc.stay_category IN ('1-4 Day Stay', '5-7 Day Stay')
GROUP BY
    apc.stay_category
ORDER BY
    apc.stay_category;
