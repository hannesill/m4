SELECT
    ROUND(STDDEV(procedure_count), 2) AS stddev_ecg_telemetry_procedures
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 81 AND 91
        AND pr.icd_code IS NOT NULL
        AND pr.icd_version IS NOT NULL
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code = '89.52' OR
                pr.icd_code = '89.54'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '4A02%' OR
                pr.icd_code LIKE '4A12%'
            ))
        )
    GROUP BY p.subject_id
) patient_procedures;
