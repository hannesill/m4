WITH
  patient_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 61 AND 71
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '786.5%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'R07%')
      )
  ),
  initial_troponin AS (
    SELECT
      c.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER(PARTITION BY c.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      patient_cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON c.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  categorized_troponin AS (
    SELECT
      hadm_id,
      valuenum,
      CASE
        WHEN valuenum < 0.014 THEN 'Normal'
        WHEN valuenum >= 0.014 AND valuenum <= 0.052 THEN 'Borderline'
        WHEN valuenum > 0.052 THEN 'Myocardial Injury'
        ELSE 'Uncategorized'
      END AS troponin_category
    FROM
      initial_troponin
    WHERE
      rn = 1
  )
SELECT
  troponin_category,
  COUNT(hadm_id) AS patient_admission_count,
  ROUND(100.0 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER (), 2) AS percentage_of_admissions
FROM
  categorized_troponin
GROUP BY
  troponin_category
ORDER BY
  CASE
    WHEN troponin_category = 'Normal' THEN 1
    WHEN troponin_category = 'Borderline' THEN 2
    WHEN troponin_category = 'Myocardial Injury' THEN 3
    ELSE 4
  END;
