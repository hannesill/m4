SELECT
    APPROX_QUANTILES(procedure_count, 100)[OFFSET(25)] AS p25_procedure_count
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 51 AND 61
        AND (
            (pr.icd_version = 9 AND pr.icd_code IN ('8952', '8954'))
            OR
            (pr.icd_version = 10 AND pr.icd_code = '4A12X4Z')
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
