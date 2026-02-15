WITH aki_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 5 AND 7 THEN '5-7 Day Stay'
        END AS stay_category,
        CASE
            WHEN i.stay_id IS NOT NULL THEN 'ICU Stay'
            ELSE 'No ICU Stay'
        END AS icu_status
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i ON a.hadm_id = i.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 38 AND 48
        AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '584%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'N17%')
        )
),
procedure_counts AS (
    SELECT
        ak.hadm_id,
        ak.stay_category,
        ak.icu_status,
        COUNT(pr.icd_code) AS num_diagnostic_procedures
    FROM
        aki_admissions AS ak
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON ak.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (pr.icd_code LIKE '87%' OR pr.icd_code LIKE '88%' OR pr.icd_code LIKE '89%'))
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B%')
        )
    GROUP BY
        ak.hadm_id, ak.stay_category, ak.icu_status
)
SELECT
    stay_category,
    icu_status,
    COUNT(hadm_id) AS num_admissions,
    ROUND(AVG(num_diagnostic_procedures), 2) AS avg_procedures,
    MIN(num_diagnostic_procedures) AS min_procedures,
    MAX(num_diagnostic_procedures) AS max_procedures
FROM
    procedure_counts
GROUP BY
    stay_category, icu_status
ORDER BY
    stay_category, icu_status;
