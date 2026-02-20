WITH hf_admissions AS (
    SELECT
        a.hadm_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 5 AND 7 THEN '5-7 Day Stay'
        END AS stay_category,
        CASE
            WHEN MIN(
                CASE
                    WHEN (d.icd_version = 9 AND d.icd_code LIKE '428%') OR (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
                    THEN d.seq_num
                    ELSE NULL
                END
            ) = 1 THEN 'Primary Diagnosis'
            ELSE 'Secondary Diagnosis'
        END AS diagnosis_type
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 67 AND 77
        AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
    GROUP BY
        a.hadm_id, a.admittime, a.dischtime
    HAVING
        COUNTIF((d.icd_version = 9 AND d.icd_code LIKE '428%') OR (d.icd_version = 10 AND d.icd_code LIKE 'I50%')) > 0
),
imaging_counts_per_admission AS (
    SELECT
        hf.hadm_id,
        hf.stay_category,
        hf.diagnosis_type,
        COUNT(proc.icd_code) AS num_imaging_procedures
    FROM
        hf_admissions AS hf
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc ON hf.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND proc.icd_code LIKE '87%')
            OR (proc.icd_version = 9 AND proc.icd_code LIKE '88%')
            OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
        )
    GROUP BY
        hf.hadm_id, hf.stay_category, hf.diagnosis_type
)
SELECT
    stay_category,
    diagnosis_type,
    COUNT(hadm_id) AS num_admissions,
    APPROX_QUANTILES(num_imaging_procedures, 100)[OFFSET(25)] AS p25_imaging_procedures,
    APPROX_QUANTILES(num_imaging_procedures, 100)[OFFSET(50)] AS p50_imaging_procedures,
    APPROX_QUANTILES(num_imaging_procedures, 100)[OFFSET(75)] AS p75_imaging_procedures
FROM
    imaging_counts_per_admission
GROUP BY
    stay_category,
    diagnosis_type
ORDER BY
    stay_category,
    diagnosis_type;
