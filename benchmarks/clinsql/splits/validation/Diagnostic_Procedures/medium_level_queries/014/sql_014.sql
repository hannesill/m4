WITH acs_admissions AS (
  SELECT
    a.hadm_id,
    p.subject_id,
    DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
    MIN(d.seq_num) AS min_acs_seq_num
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 83 AND 93
    AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
    AND (
      (d.icd_version = 9 AND d.icd_code LIKE '410%')
      OR (d.icd_version = 9 AND d.icd_code = '4111')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'I20.0%')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'I22%')
    )
  GROUP BY
    a.hadm_id, p.subject_id, length_of_stay
),
procedure_counts AS (
  SELECT
    acs.hadm_id,
    CASE
      WHEN acs.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
      WHEN acs.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day Stay'
    END AS stay_category,
    CASE
      WHEN acs.min_acs_seq_num = 1 THEN 'Primary Diagnosis'
      ELSE 'Secondary Diagnosis'
    END AS diagnosis_type,
    COUNT(proc.icd_code) AS ultrasound_count
  FROM
    acs_admissions AS acs
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
    ON acs.hadm_id = proc.hadm_id
    AND (
      (proc.icd_version = 9 AND proc.icd_code LIKE '88.7%')
      OR (proc.icd_version = 10 AND proc.icd_code LIKE 'B24%')
    )
  WHERE
    acs.length_of_stay BETWEEN 1 AND 7
  GROUP BY
    acs.hadm_id, stay_category, diagnosis_type
)
SELECT
  pc.stay_category,
  pc.diagnosis_type,
  COUNT(pc.hadm_id) AS num_admissions,
  ROUND(AVG(pc.ultrasound_count), 2) AS avg_ultrasounds_per_admission,
  MIN(pc.ultrasound_count) AS min_ultrasounds,
  MAX(pc.ultrasound_count) AS max_ultrasounds
FROM
  procedure_counts AS pc
GROUP BY
  pc.stay_category,
  pc.diagnosis_type
ORDER BY
  pc.diagnosis_type,
  pc.stay_category;
