SELECT
    ROUND(STDDEV(procedure_count), 2) AS stddev_procedure_count
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON p.subject_id = pr.subject_id
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code = '37.34' OR
                pr.icd_code LIKE '99.6%'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '025%' OR
                pr.icd_code LIKE '5A22%'
            ))
        )
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 86 AND 96
    GROUP BY
        p.subject_id
) AS patient_procedures;
