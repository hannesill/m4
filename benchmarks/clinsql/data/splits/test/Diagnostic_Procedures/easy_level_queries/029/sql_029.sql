SELECT
    APPROX_QUANTILES(procedure_count, 100)[OFFSET(25)] AS p25_procedure_count
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
        AND p.anchor_age BETWEEN 78 AND 88
        AND pr.icd_code IS NOT NULL
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '37.8%' OR
                pr.icd_code LIKE '37.9%'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '0JH60%' OR
                pr.icd_code LIKE '02H_4%' OR
                pr.icd_code LIKE '02H_6%' OR
                pr.icd_code LIKE '02H_J%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedure_counts;
