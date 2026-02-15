SELECT
    quantiles[OFFSET(3)] - quantiles[OFFSET(1)] AS iqr_valve_procedures
FROM (
    SELECT
        APPROX_QUANTILES(procedure_count, 4) AS quantiles
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
            AND p.anchor_age BETWEEN 52 AND 62
            AND pr.icd_code IS NOT NULL
            AND (
                (pr.icd_version = 9 AND (
                    pr.icd_code LIKE '35.1%' OR
                    pr.icd_code LIKE '35.2%' OR
                    pr.icd_code IN ('35.05', '35.06')
                )) OR
                (pr.icd_version = 10 AND
                 (pr.icd_code LIKE '02R%' OR pr.icd_code LIKE '02Q%') AND
                 SUBSTR(pr.icd_code, 4, 1) IN ('F', 'G', 'H', 'J')
                )
            )
        GROUP BY
            p.subject_id
    ) AS patient_procedures
) AS quantiles_calculation;
