WITH patient_cardiac_counts AS (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 76 AND 86
        AND pr.icd_code IS NOT NULL
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '37.2%'
                OR pr.icd_code LIKE '88.7%'
                OR pr.icd_code LIKE '89.5%'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE 'B2%'
                OR pr.icd_code LIKE '4A02%'
            ))
        )
    GROUP BY p.subject_id
)
SELECT
    quantiles[OFFSET(3)] - quantiles[OFFSET(1)] AS iqr_cardiac_procedures
FROM (
    SELECT
        APPROX_QUANTILES(procedure_count, 4) AS quantiles
    FROM patient_cardiac_counts
);
