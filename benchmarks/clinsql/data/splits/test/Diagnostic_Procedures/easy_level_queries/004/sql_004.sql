SELECT
    ROUND(STDDEV(procedure_count), 2) as stddev_cabg_procedures
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) as procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 41 AND 51
      AND (
        (pr.icd_version = 9 AND pr.icd_code LIKE '36.1%')
        OR
        (pr.icd_version = 10 AND pr.icd_code LIKE '021%')
      )
    GROUP BY p.subject_id
) patient_procedures;
