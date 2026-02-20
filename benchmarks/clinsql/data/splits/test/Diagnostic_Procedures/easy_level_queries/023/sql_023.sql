SELECT
    APPROX_QUANTILES(procedure_count, 4)[OFFSET(1)] AS p25_cardiac_procedures
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
        AND p.anchor_age BETWEEN 82 AND 92
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '37.2%'
                OR pr.icd_code = '88.72'
                OR pr.icd_code = '89.52'
                OR pr.icd_code LIKE '89.4%'
            ))
            OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE 'B21%'
                OR pr.icd_code LIKE '4A0%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_cardiac_procedures;
