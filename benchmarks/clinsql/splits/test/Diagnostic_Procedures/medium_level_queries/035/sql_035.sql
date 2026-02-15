WITH aki_admissions AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
    MAX(CASE WHEN d.seq_num = 1 THEN 1 ELSE 0 END) AS is_primary_aki_flag
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
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 43 AND 53
    AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
    AND (
      (d.icd_version = 9 AND d.icd_code LIKE '584%') OR
      (d.icd_version = 10 AND d.icd_code LIKE 'N17%')
    )
  GROUP BY
    p.subject_id,
    a.hadm_id,
    length_of_stay
),

procedure_counts AS (
  SELECT
    aki.subject_id,
    aki.hadm_id,
    CASE
      WHEN aki.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day LOS'
      WHEN aki.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day LOS'
      ELSE NULL
    END AS los_group,
    CASE
      WHEN aki.is_primary_aki_flag = 1 THEN 'Primary Diagnosis'
      ELSE 'Secondary Diagnosis'
    END AS diagnosis_type,
    COUNT(pr.icd_code) AS imaging_count
  FROM
    aki_admissions AS aki
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
    ON aki.hadm_id = pr.hadm_id
    AND (
      (pr.icd_version = 9 AND pr.icd_code IN ('87.03', '87.41', '87.71', '88.01', '88.38', '88.91', '88.92', '88.93', '88.94', '88.95', '88.96', '88.97'))
      OR
      (pr.icd_version = 10 AND (pr.icd_code LIKE 'B2%' OR pr.icd_code LIKE 'B3%'))
    )
  GROUP BY
    aki.subject_id,
    aki.hadm_id,
    los_group,
    diagnosis_type
)

SELECT
  pc.los_group,
  pc.diagnosis_type,
  COUNT(DISTINCT pc.subject_id) AS patient_count,
  ROUND(AVG(pc.imaging_count), 2) AS avg_mri_ct_per_admission
FROM
  procedure_counts AS pc
WHERE
  pc.los_group IS NOT NULL
GROUP BY
  pc.los_group,
  pc.diagnosis_type
ORDER BY
  pc.los_group,
  pc.diagnosis_type;
