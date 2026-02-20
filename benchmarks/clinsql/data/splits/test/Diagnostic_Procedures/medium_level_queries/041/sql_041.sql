WITH pancreatitis_admissions AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE
            WHEN d.seq_num = 1 THEN 'Primary Diagnosis'
            ELSE 'Secondary Diagnosis'
        END AS diagnosis_type,
        ROW_NUMBER() OVER(PARTITION BY a.hadm_id ORDER BY d.seq_num ASC) as diagnosis_rank
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 51 AND 61
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND d.icd_code = '577.0')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
        )
), imaging_counts AS (
    SELECT
        pa.subject_id,
        pa.hadm_id,
        pa.length_of_stay,
        pa.diagnosis_type,
        COUNT(proc.icd_code) AS radiography_ct_count
    FROM
        pancreatitis_admissions pa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` proc ON pa.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND (proc.icd_code LIKE '87%' OR proc.icd_code LIKE '88%'))
            OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
        )
    WHERE
        pa.diagnosis_rank = 1
    GROUP BY
        pa.subject_id,
        pa.hadm_id,
        pa.length_of_stay,
        pa.diagnosis_type
)
SELECT
    CASE
        WHEN ic.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Days'
        WHEN ic.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Days'
    END AS length_of_stay_group,
    ic.diagnosis_type,
    COUNT(DISTINCT ic.subject_id) AS patient_count,
    ROUND(AVG(ic.radiography_ct_count), 2) AS avg_radiography_ct_per_admission
FROM
    imaging_counts ic
GROUP BY
    length_of_stay_group,
    ic.diagnosis_type
ORDER BY
    length_of_stay_group,
    ic.diagnosis_type;
