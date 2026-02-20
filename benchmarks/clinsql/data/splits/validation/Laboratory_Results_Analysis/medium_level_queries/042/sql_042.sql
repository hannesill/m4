WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.hospital_expire_flag,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS admission_age
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND a.admittime IS NOT NULL
),
chest_pain_admissions AS (
  SELECT DISTINCT
    pc.hadm_id,
    pc.hospital_expire_flag
  FROM
    patient_cohort AS pc
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON pc.hadm_id = dx.hadm_id
  WHERE
    pc.admission_age BETWEEN 84 AND 94
    AND (
      (dx.icd_version = 9 AND dx.icd_code LIKE '786.5%')
      OR
      (dx.icd_version = 10 AND dx.icd_code LIKE 'R07%')
    )
),
first_troponin AS (
  SELECT
    cpa.hadm_id,
    cpa.hospital_expire_flag,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    chest_pain_admissions AS cpa
  JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON cpa.hadm_id = le.hadm_id
  WHERE
    le.itemid = 51003
    AND le.valuenum IS NOT NULL
    AND le.valuenum >= 0
),
categorized_troponin AS (
  SELECT
    hadm_id,
    hospital_expire_flag,
    CASE
      WHEN valuenum <= 0.04 THEN 'Normal'
      WHEN valuenum > 0.04 AND valuenum <= 0.1 THEN 'Borderline'
      WHEN valuenum > 0.1 THEN 'Elevated'
      ELSE 'Unknown'
    END AS troponin_category
  FROM
    first_troponin
  WHERE
    rn = 1
)
SELECT
  troponin_category,
  COUNT(hadm_id) AS patient_count,
  ROUND(COUNT(hadm_id) * 100.0 / SUM(COUNT(hadm_id)) OVER(), 2) AS percentage_of_total,
  ROUND(AVG(hospital_expire_flag) * 100.0, 2) AS in_hospital_mortality_rate_percent
FROM
  categorized_troponin
WHERE
  troponin_category != 'Unknown'
GROUP BY
  troponin_category
ORDER BY
  CASE
    WHEN troponin_category = 'Normal' THEN 1
    WHEN troponin_category = 'Borderline' THEN 2
    WHEN troponin_category = 'Elevated' THEN 3
  END;
