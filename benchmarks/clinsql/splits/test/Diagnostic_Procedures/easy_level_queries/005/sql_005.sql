SELECT
    APPROX_QUANTILES(procedure_count, 100)[OFFSET(75)] AS p75_distinct_echo_procedures
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
        AND p.anchor_age BETWEEN 57 AND 67
        AND (
            (pr.icd_version = 9 AND pr.icd_code = '88.72')
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE 'B21%')
        )
    GROUP BY
        p.subject_id
) patient_procedures;
