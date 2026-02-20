WITH hf_admissions AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) as length_of_stay,
        MIN(d.seq_num) as hf_min_seq_num
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 45 AND 55
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '428%') OR
            (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
        )
    GROUP BY
        a.hadm_id,
        length_of_stay
    HAVING
        length_of_stay BETWEEN 1 AND 7
),
imaging_counts AS (
    SELECT
        hf.hadm_id,
        hf.length_of_stay,
        hf.hf_min_seq_num,
        COUNT(proc.icd_code) as imaging_procedure_count
    FROM
        hf_admissions hf
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` proc ON hf.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND (proc.icd_code LIKE '88.0%' OR proc.icd_code LIKE '88.9%')) OR
            (proc.icd_version = 10 AND (proc.icd_code LIKE 'B_2%' OR proc.icd_code LIKE 'B_3%'))
        )
    GROUP BY
        hf.hadm_id,
        hf.length_of_stay,
        hf.hf_min_seq_num
)
SELECT
    CASE
        WHEN hf_min_seq_num = 1 THEN 'Primary Diagnosis'
        ELSE 'Secondary Diagnosis'
    END AS diagnosis_type,
    CASE
        WHEN length_of_stay BETWEEN 1 AND 3 THEN '1-3 Day Stay'
        ELSE '4-7 Day Stay'
    END AS stay_category,
    COUNT(hadm_id) as total_admissions,
    ROUND(AVG(imaging_procedure_count), 2) as mean_imaging_procedures,
    MIN(imaging_procedure_count) as min_imaging_procedures,
    MAX(imaging_procedure_count) as max_imaging_procedures
FROM
    imaging_counts
GROUP BY
    diagnosis_type,
    stay_category
ORDER BY
    diagnosis_type DESC,
    stay_category;
