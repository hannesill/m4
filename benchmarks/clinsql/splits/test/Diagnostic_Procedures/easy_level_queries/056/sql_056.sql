SELECT
    APPROX_QUANTILES(procedure_count, 4)[OFFSET(1)] AS p25_mech_circ_support_count
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT mcs_proc.icd_code) AS procedure_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS mcs_proc
    ON
        p.subject_id = mcs_proc.subject_id
        AND (
            (mcs_proc.icd_version = 9 AND mcs_proc.icd_code IN (
                '37.61',
                '37.62',
                '37.63',
                '37.64',
                '37.65',
                '37.66',
                '37.68'
            ))
            OR
            (mcs_proc.icd_version = 10 AND (
                mcs_proc.icd_code LIKE '5A02%' OR
                mcs_proc.icd_code LIKE '5A09%'
            ))
        )
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 43 AND 53
    GROUP BY
        p.subject_id
) AS patient_procedure_counts;
