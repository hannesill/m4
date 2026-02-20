WITH patient_procedure_counts AS (
  SELECT
    p.subject_id,
    COUNT(DISTINCT pe.itemid) AS procedure_count
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
    ON p.subject_id = pe.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 73 AND 83
    AND pe.itemid IN (
      224154,
      225443,
      228177,
      225309,
      225308,
      225301,
      225302,
      225303,
      225304,
      225305
    )
    AND p.subject_id IS NOT NULL
    AND p.anchor_age IS NOT NULL
    AND pe.itemid IS NOT NULL
  GROUP BY
    p.subject_id
)
SELECT
  APPROX_QUANTILES(procedure_count, 2)[OFFSET(1)] AS median_mechanical_support_count
FROM
  patient_procedure_counts;
