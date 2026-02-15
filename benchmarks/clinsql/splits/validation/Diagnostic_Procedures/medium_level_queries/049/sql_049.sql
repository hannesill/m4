WITH sepsis_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) as length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 87 AND 97
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
    GROUP BY
        a.hadm_id, a.subject_id, length_of_stay
    HAVING
        COUNTIF(
            (d.icd_version = 9 AND d.icd_code = '99591') OR
            (d.icd_version = 10 AND STARTS_WITH(d.icd_code, 'A41'))
        ) > 0
        AND COUNTIF(
            (d.icd_version = 9 AND d.icd_code = '78552') OR
            (d.icd_version = 10 AND d.icd_code = 'R6521')
        ) = 0
),
procedure_counts AS (
    SELECT
        sa.hadm_id,
        CASE
            WHEN sa.length_of_stay BETWEEN 1 AND 3 THEN '1-3 days'
            WHEN sa.length_of_stay BETWEEN 4 AND 7 THEN '4-7 days'
            ELSE 'Other'
        END AS stay_category,
        COUNT(pr.icd_code) AS diagnostic_procedure_count
    FROM
        sepsis_admissions sa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON sa.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (STARTS_WITH(pr.icd_code, '87') OR STARTS_WITH(pr.icd_code, '88')))
            OR (pr.icd_version = 10 AND STARTS_WITH(pr.icd_code, 'B'))
        )
    GROUP BY
        sa.hadm_id, sa.length_of_stay
)
SELECT
    stay_category,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(diagnostic_procedure_count), 2) AS mean_diagnostic_procedures,
    MIN(diagnostic_procedure_count) AS min_diagnostic_procedures,
    MAX(diagnostic_procedure_count) AS max_diagnostic_procedures
FROM
    procedure_counts
WHERE
    stay_category IN ('1-3 days', '4-7 days')
GROUP BY
    stay_category
ORDER BY
    stay_category;
