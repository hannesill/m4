WITH stroke_admissions AS (
    SELECT
        hadm_id,
        subject_id,
        length_of_stay,
        diagnosis_type
    FROM (
        SELECT
            a.hadm_id,
            a.subject_id,
            DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
            CASE
                WHEN d.seq_num = 1 THEN 'Primary Diagnosis'
                ELSE 'Secondary Diagnosis'
            END AS diagnosis_type,
            ROW_NUMBER() OVER(PARTITION BY a.hadm_id ORDER BY d.seq_num ASC) as diagnosis_rank
        FROM
            `physionet-data.mimiciv_3_1_hosp.patients` AS p
        INNER JOIN
            `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
        INNER JOIN
            `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
        WHERE
            p.gender = 'F'
            AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 49 AND 59
            AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
            AND (
                (d.icd_version = 9 AND d.icd_code LIKE '434%')
                OR (d.icd_version = 10 AND d.icd_code LIKE 'I63%')
            )
            AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
    )
    WHERE
        diagnosis_rank = 1
),
procedure_counts AS (
    SELECT
        sa.hadm_id,
        sa.diagnosis_type,
        CASE
            WHEN sa.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN sa.length_of_stay BETWEEN 5 AND 8 THEN '5-8 Day Stay'
        END AS stay_category,
        COUNT(proc.icd_code) AS num_procedures
    FROM
        stroke_admissions AS sa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc ON sa.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND proc.icd_code LIKE '87%')
            OR (proc.icd_version = 9 AND proc.icd_code LIKE '88%')
            OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
        )
    GROUP BY
        sa.hadm_id,
        sa.diagnosis_type,
        stay_category
)
SELECT
    pc.stay_category,
    pc.diagnosis_type,
    COUNT(DISTINCT pc.hadm_id) AS num_admissions,
    ROUND(AVG(pc.num_procedures), 2) AS avg_procedures_per_admission,
    MIN(pc.num_procedures) AS min_procedures_per_admission,
    MAX(pc.num_procedures) AS max_procedures_per_admission
FROM
    procedure_counts AS pc
GROUP BY
    pc.stay_category,
    pc.diagnosis_type
ORDER BY
    pc.stay_category,
    pc.diagnosis_type;
