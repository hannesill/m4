WITH
  patient_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND a.admittime IS NOT NULL
  ),
  acs_cohort AS (
    SELECT DISTINCT
      pa.hadm_id,
      pa.hospital_expire_flag
    FROM
      patient_admissions AS pa
    JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON pa.hadm_id = d.hadm_id
    WHERE
      pa.age_at_admission BETWEEN 67 AND 77
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
        OR
        (d.icd_version = 10 AND (
            d.icd_code LIKE 'I21%'
            OR d.icd_code LIKE 'I22%'
            OR d.icd_code = 'I200'
            OR d.icd_code = 'I248'
            OR d.icd_code = 'I249'
          )
        )
      )
  ),
  initial_troponin AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      l.valuenum,
      ROW_NUMBER() OVER(PARTITION BY c.hadm_id ORDER BY l.charttime ASC) AS rn
    FROM
      acs_cohort AS c
    JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS l
      ON c.hadm_id = l.hadm_id
    WHERE
      l.itemid = 51003
      AND l.valuenum IS NOT NULL
      AND l.valuenum >= 0
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
      initial_troponin
    WHERE
      rn = 1
  )
SELECT
  troponin_category,
  COUNT(hadm_id) AS patient_admission_count,
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
