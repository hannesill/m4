WITH pancreatitis_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) as length_of_stay,
        MIN(d.seq_num) as pancreatitis_seq_num
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 52 AND 62
        AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
        AND (
            (d.icd_version = 9 AND d.icd_code = '5770')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
        )
    GROUP BY
        a.hadm_id, a.subject_id, length_of_stay
),
procedure_counts AS (
    SELECT
        pa.hadm_id,
        CASE
            WHEN pa.length_of_stay BETWEEN 1 AND 4 THEN '1-4 days'
            WHEN pa.length_of_stay BETWEEN 5 AND 8 THEN '5-8 days'
        END AS stay_category,
        CASE
            WHEN pa.pancreatitis_seq_num = 1 THEN 'Primary Diagnosis'
            ELSE 'Secondary Diagnosis'
        END AS diagnosis_type,
        COUNT(proc.icd_code) AS num_procedures
    FROM
        pancreatitis_admissions AS pa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
        ON pa.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND (proc.icd_code LIKE '87%' OR proc.icd_code LIKE '88%'))
            OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
        )
    GROUP BY
        pa.hadm_id, stay_category, diagnosis_type
)
SELECT
    stay_category,
    diagnosis_type,
    COUNT(hadm_id) AS num_admissions,
    ROUND(AVG(num_procedures), 2) AS avg_procedures_per_admission,
    MIN(num_procedures) AS min_procedures,
    MAX(num_procedures) AS max_procedures
FROM
    procedure_counts
GROUP BY
    stay_category, diagnosis_type
ORDER BY
    stay_category, diagnosis_type;
