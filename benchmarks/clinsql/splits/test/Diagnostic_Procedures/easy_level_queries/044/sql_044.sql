SELECT
    ROUND(STDDEV(procedure_count), 2) as stddev_mech_circ_support_procedures
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) as procedure_count
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE p.gender = 'M'
      AND p.anchor_age BETWEEN 56 AND 66
      AND pr.icd_code IS NOT NULL
      AND (
        (pr.icd_version = 9 AND (
          pr.icd_code LIKE '37.6%'
        )) OR
        (pr.icd_version = 10 AND (
          pr.icd_code LIKE '5A02%' OR
          pr.icd_code LIKE '5A1522%'
        ))
      )
    GROUP BY p.subject_id
) patient_procedures;
