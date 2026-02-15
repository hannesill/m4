SELECT
    APPROX_QUANTILES(procedure_count, 100)[OFFSET(75)] AS percentile_75th_ecg_telemetry
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
        AND p.anchor_age BETWEEN 75 AND 85
        AND (
            (pr.icd_version = 9 AND pr.icd_code IN ('8952', '8954'))
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE '4A12X4%')
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
