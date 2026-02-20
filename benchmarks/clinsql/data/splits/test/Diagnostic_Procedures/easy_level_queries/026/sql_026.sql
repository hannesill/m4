WITH patient_procedure_counts AS (
  SELECT
    p.subject_id,
    COUNT(DISTINCT pr.icd_code) AS procedure_count
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
    ON p.subject_id = pr.subject_id
    AND (
      (pr.icd_version = 9 AND (
        pr.icd_code = '37.34'
        OR pr.icd_code LIKE '99.6%'
      ))
      OR
      (pr.icd_version = 10 AND (
        pr.icd_code LIKE '025%'
        OR pr.icd_code LIKE '5A22%'
      ))
    )
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 75 AND 85
  GROUP BY
    p.subject_id
)
SELECT
  (APPROX_QUANTILES(procedure_count, 4)[OFFSET(3)] - APPROX_QUANTILES(procedure_count, 4)[OFFSET(1)]) AS iqr_procedure_count
FROM
  patient_procedure_counts;
