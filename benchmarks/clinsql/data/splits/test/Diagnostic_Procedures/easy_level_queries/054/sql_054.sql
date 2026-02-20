SELECT
    MAX(procedure_count) AS max_distinct_echo_procedures
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 81 AND 91
        AND (
            (pr.icd_version = 9 AND pr.icd_code = '88.72')
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE 'B21%')
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
