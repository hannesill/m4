SELECT
    MIN(procedure_count) as min_cardiac_cath_procedures
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) as procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 64 AND 74
        AND pr.icd_code IS NOT NULL
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '37.21' OR
                pr.icd_code LIKE '37.22' OR
                pr.icd_code LIKE '37.23'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '4A02%'
            ))
        )
    GROUP BY p.subject_id
) patient_procedures;
