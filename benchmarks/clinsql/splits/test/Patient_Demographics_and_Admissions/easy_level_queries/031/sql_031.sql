WITH hf_admissions AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 38 AND 48
    AND a.dischtime IS NOT NULL
    AND (
      (d.icd_version = 9 AND d.icd_code LIKE '428%') OR
      (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
    )
),
ranked_admissions AS (
  SELECT
    subject_id,
    admittime,
    dischtime,
    LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime ASC) AS next_admittime,
    ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY admittime ASC) AS admission_rank
  FROM
    hf_admissions
),
first_admission_readmission_flag AS (
  SELECT
    subject_id,
    CASE
      WHEN next_admittime IS NOT NULL AND DATE_DIFF(DATE(next_admittime), DATE(dischtime), DAY) <= 30 THEN 1
      ELSE 0
    END AS is_readmitted_within_30_days
  FROM
    ranked_admissions
  WHERE
    admission_rank = 1
)
SELECT
  AVG(is_readmitted_within_30_days) AS avg_30_day_readmission_rate
FROM
  first_admission_readmission_flag;
