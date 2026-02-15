SELECT
    CAST(APPROX_QUANTILES(procedure_count, 100)[OFFSET(75)] AS INT64) AS p75_ecg_telemetry_count
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
        AND p.anchor_age BETWEEN 41 AND 51
        AND (
            (pr.icd_version = 9 AND pr.icd_code IN (
                '89.52',
                '89.61'
            ))
            OR
            (pr.icd_version = 10 AND pr.icd_code IN (
                '4A02XN7',
                '4A023N7'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
