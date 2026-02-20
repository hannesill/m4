SELECT
    APPROX_QUANTILES(procedure_count, 4)[OFFSET(3)] AS p75_procedure_count
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
        AND p.anchor_age BETWEEN 58 AND 68
        AND pr.icd_code IS NOT NULL
        AND (
            (pr.icd_version = 9 AND pr.icd_code IN (
                '88.55',
                '88.56',
                '88.57',
                '00.66',
                '36.06',
                '36.07',
                '36.09'
            ))
            OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE 'B211%'
                OR pr.icd_code LIKE '027%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
