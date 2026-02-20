SELECT
    APPROX_QUANTILES(procedure_count, 100)[OFFSET(75)] AS p75_cardiac_procedures
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
        AND p.anchor_age BETWEEN 63 AND 73
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '35%' OR
                pr.icd_code LIKE '36%' OR
                pr.icd_code LIKE '37%' OR
                pr.icd_code LIKE '88.72' OR
                pr.icd_code LIKE '89.52'
            ))
            OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '02%' OR
                pr.icd_code LIKE 'B2%' OR
                pr.icd_code LIKE '4A12%' OR
                pr.icd_code LIKE '4A02%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
