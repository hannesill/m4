SELECT
    ROUND(AVG(procedure_count), 2) AS avg_valve_procedures
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
        AND p.anchor_age BETWEEN 42 AND 52
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '35.1%' OR
                pr.icd_code LIKE '35.2%' OR
                pr.icd_code IN ('35.05', '35.06', '35.07', '35.08')
            )) OR
            (pr.icd_version = 10 AND
                SUBSTR(pr.icd_code, 1, 4) IN (
                    '02PF', '02PG', '02PH', '02PJ',
                    '02RF', '02RG', '02RH', '02RJ'
                )
            )
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
