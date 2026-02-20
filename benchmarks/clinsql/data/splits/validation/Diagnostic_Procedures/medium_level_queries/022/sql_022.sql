WITH hf_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 4 THEN '1-4 days'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 5 AND 7 THEN '5-7 days'
        END AS stay_category,
        CASE
            WHEN a.admission_type IN ('EMERGENCY', 'URGENT') THEN 'ED/Urgent'
            WHEN a.admission_type = 'ELECTIVE' THEN 'Elective'
            ELSE 'Other'
        END AS admission_category
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 69 AND 79
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '428%') OR
            (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
        )
),
procedure_counts AS (
    SELECT
        hf.hadm_id,
        hf.stay_category,
        hf.admission_category,
        COUNT(pr.icd_code) AS num_diagnostic_procedures
    FROM
        hf_admissions AS hf
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON hf.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '87%' OR
                pr.icd_code LIKE '88%' OR
                pr.icd_code = '89.52' OR
                pr.icd_code = '89.14' OR
                pr.icd_code = '89.37'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE 'B%' OR
                pr.icd_code LIKE '4A%'
            ))
        )
    GROUP BY
        hf.hadm_id, hf.stay_category, hf.admission_category
)
SELECT
    pc.stay_category,
    pc.admission_category,
    COUNT(pc.hadm_id) AS number_of_admissions,
    ROUND(AVG(pc.num_diagnostic_procedures), 2) AS avg_diagnostics_per_admission,
    MIN(pc.num_diagnostic_procedures) AS min_diagnostics_per_admission,
    MAX(pc.num_diagnostic_procedures) AS max_diagnostics_per_admission
FROM
    procedure_counts pc
WHERE
    pc.admission_category IN ('ED/Urgent', 'Elective')
GROUP BY
    pc.stay_category, pc.admission_category
ORDER BY
    pc.stay_category, pc.admission_category;
