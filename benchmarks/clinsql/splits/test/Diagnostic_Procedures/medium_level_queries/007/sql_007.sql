WITH admission_details AS (
  SELECT
    a.hadm_id,
    CASE
      WHEN MIN(d.seq_num) = 1 THEN 'Primary Diagnosis'
      ELSE 'Secondary Diagnosis'
    END AS diagnosis_type,
    CASE
      WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 4 THEN '1-4 days'
      WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 5 AND 8 THEN '5-8 days'
    END AS los_category
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
    AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
    AND (
      (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code IN ('4111', '41181')))
      OR (d.icd_version = 10 AND (
          d.icd_code LIKE 'I200%' OR
          d.icd_code LIKE 'I21%' OR
          d.icd_code LIKE 'I22%' OR
          d.icd_code IN ('I240', 'I248', 'I249')
        ))
    )
  GROUP BY
    a.hadm_id, a.admittime, a.dischtime
),
procedure_counts AS (
  SELECT
    ad.hadm_id,
    ad.los_category,
    ad.diagnosis_type,
    COUNT(proc.icd_code) AS num_diagnostic_procedures
  FROM
    admission_details AS ad
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
    ON ad.hadm_id = proc.hadm_id
    AND (
      (proc.icd_version = 9 AND (proc.icd_code LIKE '87%' OR proc.icd_code LIKE '88%'))
      OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
    )
  GROUP BY
    ad.hadm_id, ad.los_category, ad.diagnosis_type
)
SELECT
  diagnosis_type,
  los_category,
  COUNT(hadm_id) AS num_admissions,
  APPROX_QUANTILES(num_diagnostic_procedures, 4)[OFFSET(1)] AS p25_procedures,
  APPROX_QUANTILES(num_diagnostic_procedures, 4)[OFFSET(2)] AS p50_median_procedures,
  APPROX_QUANTILES(num_diagnostic_procedures, 4)[OFFSET(3)] AS p75_procedures
FROM
  procedure_counts
GROUP BY
  diagnosis_type,
  los_category
ORDER BY
  diagnosis_type,
  los_category;
