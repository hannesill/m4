WITH patient_procedure_counts AS (
  SELECT
    p.subject_id,
    COUNT(DISTINCT pr.icd_code) AS procedure_count
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr
    ON p.subject_id = pr.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 86 AND 96
    AND (
      (pr.icd_version = 9 AND pr.icd_code LIKE '37.6%')
      OR
      (pr.icd_version = 10 AND pr.icd_code LIKE '5A02%')
    )
  GROUP BY
    p.subject_id
)
SELECT
  IFNULL(
    (APPROX_QUANTILES(procedure_count, 4)[OFFSET(3)] - APPROX_QUANTILES(procedure_count, 4)[OFFSET(1)]),
    0
  ) AS iqr_mechanical_circulatory_support
FROM
  patient_procedure_counts;
