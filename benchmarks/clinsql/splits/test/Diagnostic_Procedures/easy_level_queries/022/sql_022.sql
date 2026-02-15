SELECT
    MIN(procedure_count) as min_pacemaker_or_icd_implantations
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) as procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 82 AND 92
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '37.8%' OR
                pr.icd_code = '37.94' OR
                pr.icd_code = '37.95' OR
                pr.icd_code = '37.96'
            )) OR
            (pr.icd_version = 10 AND (
                pr.icd_code LIKE '0JH6%' OR
                pr.icd_code LIKE '0JH8%' OR
                pr.icd_code LIKE '0JHT%' OR
                pr.icd_code LIKE '0JHW%'
            ))
        )
    GROUP BY
        p.subject_id
) AS patient_procedures;
