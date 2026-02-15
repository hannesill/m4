SELECT
    APPROX_QUANTILES(cabg_procedure_count, 100)[OFFSET(25)] AS p25_cabg_count
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS cabg_procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 45 AND 55
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '36.1%')
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE '021%')
        )
        AND pr.icd_code IS NOT NULL
        AND pr.icd_version IS NOT NULL
    GROUP BY
        p.subject_id
) AS patient_procedure_counts;
