SELECT
    MIN(procedure_count) as min_mechanical_circulatory_support
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) as procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 40 AND 50
        AND (
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '5A0%'
                OR pr.icd_code LIKE '5A1%'
            ))
            OR
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '37.6%'
                OR pr.icd_code = '39.65'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedure_counts;
