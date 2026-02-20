WITH tia_admissions AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
    DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 90 AND 100
    AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
    AND (
      (d.icd_version = 9 AND d.icd_code LIKE '435%')
      OR
      (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
    )
),
procedure_counts AS (
  SELECT
    tia.hadm_id,
    tia.length_of_stay,
    CASE
      WHEN tia.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Day Stay'
      WHEN tia.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Day Stay'
      ELSE 'Other Stay Duration'
    END AS stay_category,
    COUNT(proc.icd_code) AS imaging_procedure_count
  FROM
    tia_admissions AS tia
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
    ON tia.hadm_id = proc.hadm_id
    AND (
      (proc.icd_version = 9 AND proc.icd_code LIKE '87%')
      OR (proc.icd_version = 9 AND proc.icd_code LIKE '88%')
      OR
      (proc.icd_version = 10 AND proc.icd_code LIKE 'B%')
    )
  GROUP BY
    tia.hadm_id,
    tia.length_of_stay
)
SELECT
  stay_category,
  COUNT(hadm_id) AS total_admissions,
  ROUND(AVG(imaging_procedure_count), 2) AS avg_imaging_procedures_per_admission,
  MIN(imaging_procedure_count) AS min_imaging_procedures,
  MAX(imaging_procedure_count) AS max_imaging_procedures
FROM
  procedure_counts
WHERE
  stay_category IN ('1-3 Day Stay', '4-7 Day Stay')
GROUP BY
  stay_category
ORDER BY
  stay_category;
