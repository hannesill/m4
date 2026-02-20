WITH ami_admissions AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        d.seq_num,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 43 AND 53
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '410%')
            OR (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%'))
        )
),
procedure_counts AS (
    SELECT
        adm.hadm_id,
        CASE
            WHEN MIN(adm.seq_num) = 1 THEN 'Primary AMI'
            ELSE 'Secondary AMI'
        END AS diagnosis_type,
        CASE
            WHEN adm.length_of_stay BETWEEN 1 AND 3 THEN '1-3 days'
            ELSE '4-7 days'
        END AS stay_category,
        COUNT(pr.icd_code) AS num_procedures
    FROM
        ami_admissions AS adm
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON adm.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '87%')
            OR (pr.icd_version = 10 AND SUBSTR(pr.icd_code, 1, 1) = 'B' AND SUBSTR(pr.icd_code, 3, 1) IN ('0', '2'))
        )
    GROUP BY
        adm.hadm_id, adm.length_of_stay
)
SELECT
    diagnosis_type,
    stay_category,
    COUNT(hadm_id) AS num_admissions,
    APPROX_QUANTILES(num_procedures, 100)[OFFSET(25)] AS procedures_p25,
    APPROX_QUANTILES(num_procedures, 100)[OFFSET(50)] AS procedures_median,
    APPROX_QUANTILES(num_procedures, 100)[OFFSET(75)] AS procedures_p75,
    (APPROX_QUANTILES(num_procedures, 100)[OFFSET(75)] - APPROX_QUANTILES(num_procedures, 100)[OFFSET(25)]) AS procedures_iqr
FROM
    procedure_counts
GROUP BY
    diagnosis_type, stay_category
ORDER BY
    diagnosis_type, stay_category;
