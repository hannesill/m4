WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS admission_age
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
  ),
  acs_admissions AS (
    SELECT DISTINCT
      pc.subject_id,
      pc.hadm_id
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON pc.hadm_id = d.hadm_id
    WHERE
      pc.admission_age BETWEEN 79 AND 89
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
        OR
        (d.icd_version = 10 AND (d.icd_code LIKE 'I20.0%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%'))
      )
  ),
  index_troponin AS (
    SELECT
      aa.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY aa.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      acs_admissions AS aa
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON aa.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  )
SELECT
  CASE
    WHEN valuenum <= 0.04 THEN 'Normal (<= 0.04 ng/mL)'
    WHEN valuenum > 0.04 AND valuenum <= 0.1 THEN 'Borderline (> 0.04 to 0.1 ng/mL)'
    WHEN valuenum > 0.1 THEN 'Elevated (> 0.1 ng/mL)'
    ELSE 'Unknown'
  END AS troponin_category,
  COUNT(hadm_id) AS admission_count
FROM
  index_troponin
WHERE
  rn = 1
GROUP BY
  troponin_category
ORDER BY
  CASE
    WHEN troponin_category LIKE 'Normal%' THEN 1
    WHEN troponin_category LIKE 'Borderline%' THEN 2
    WHEN troponin_category LIKE 'Elevated%' THEN 3
    ELSE 4
  END;
