SELECT
    ROUND(STDDEV(procedure_count), 2) as stddev_procedure_count
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) as procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 37 AND 47
        AND (
            (pr.icd_version = 9 AND pr.icd_code IN (
                '99.60',
                '99.61',
                '99.62',
                '99.69',
                '37.34'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '5A22%' OR
                pr.icd_code LIKE '0258%'
            ))
        )
    GROUP BY p.subject_id
) patient_procedures;
