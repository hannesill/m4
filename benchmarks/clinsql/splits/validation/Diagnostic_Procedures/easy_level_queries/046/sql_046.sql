SELECT
    MAX(procedure_count) AS max_mechanical_circulatory_support_count
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
        p.gender = 'M'
        AND p.anchor_age BETWEEN 80 AND 90
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '37.6%')
            OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '5A02%' OR
                pr.icd_code LIKE '02HL%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedure_counts;
