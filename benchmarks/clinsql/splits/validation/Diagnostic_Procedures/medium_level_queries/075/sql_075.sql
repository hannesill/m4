WITH acs_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 days'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 days'
        END AS stay_category,
        CASE
            WHEN MIN(d.seq_num) = 1 THEN 'Primary Diagnosis'
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 59 AND 69
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
            OR
            (d.icd_version = 10 AND (
                d.icd_code = 'I200' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%' OR
                d.icd_code IN ('I240', 'I248', 'I249')
            ))
        )
    GROUP BY
        a.hadm_id, a.subject_id, a.admittime, a.dischtime
),

procedure_counts AS (
    SELECT
        acs.hadm_id,
        acs.stay_category,
        acs.diagnosis_type,
        COUNT(pr.icd_code) AS num_diagnostic_procedures
    FROM
        acs_admissions AS acs
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON acs.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%'))
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    GROUP BY
        acs.hadm_id,
        acs.stay_category,
        acs.diagnosis_type
)

SELECT
    diagnosis_type,
    stay_category,
    COUNT(hadm_id) AS admission_count,
    APPROX_QUANTILES(num_diagnostic_procedures, 100)[OFFSET(25)] AS p25_procedures,
    APPROX_QUANTILES(num_diagnostic_procedures, 100)[OFFSET(50)] AS p50_median_procedures,
    APPROX_QUANTILES(num_diagnostic_procedures, 100)[OFFSET(75)] AS p75_procedures
FROM
    procedure_counts
GROUP BY
    diagnosis_type,
    stay_category
ORDER BY
    diagnosis_type,
    stay_category;
