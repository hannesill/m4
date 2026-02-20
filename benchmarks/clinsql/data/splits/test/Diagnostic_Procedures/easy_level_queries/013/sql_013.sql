SELECT
    MIN(procedure_count) AS min_valve_procedures
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 57 AND 67
        AND pr.icd_code IS NOT NULL
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '35.1%' OR
                pr.icd_code LIKE '35.2%' OR
                pr.icd_code = '35.05' OR
                pr.icd_code = '35.06' OR
                pr.icd_code = '35.07' OR
                pr.icd_code = '35.08' OR
                pr.icd_code = '35.96'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '02RF%' OR
                pr.icd_code LIKE '02UF%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
