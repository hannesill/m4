WITH hf_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) as length_of_stay,
        MIN(d.seq_num) as min_hf_seq_num
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 90 AND 100
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '428%') OR
            (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
        )
    GROUP BY
        a.hadm_id, a.subject_id, length_of_stay
),
imaging_per_admission AS (
    SELECT
        hf.hadm_id,
        CASE
            WHEN hf.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            WHEN hf.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Day Stay'
        END AS stay_group,
        CASE
            WHEN hf.min_hf_seq_num = 1 THEN 'Primary Diagnosis'
            ELSE 'Secondary Diagnosis'
        END AS diagnosis_type,
        COUNT(pr.icd_code) AS imaging_count
    FROM
        hf_admissions AS hf
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON hf.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 10 AND (pr.icd_code LIKE 'B_0%' OR pr.icd_code LIKE 'B_1%')) OR
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '87.0%' OR
                pr.icd_code LIKE '87.4%' OR
                pr.icd_code LIKE '88.0%' OR
                pr.icd_code LIKE '88.3%' OR
                pr.icd_code LIKE '88.9%'
            ))
        )
    GROUP BY
        hf.hadm_id, stay_group, diagnosis_type
)
SELECT
    stay_group,
    diagnosis_type,
    COUNT(hadm_id) AS admission_count,
    ROUND(AVG(imaging_count), 2) AS avg_mri_ct_per_admission
FROM
    imaging_per_admission
GROUP BY
    stay_group, diagnosis_type
ORDER BY
    diagnosis_type, stay_group;
