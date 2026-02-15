WITH
  ami_patient_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 40 AND 50
      AND (
        d.icd_code LIKE '410%'
        OR d.icd_code LIKE 'I21%'
      )
  ),
  initial_troponin_t AS (
    SELECT
      cohort.subject_id,
      cohort.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY cohort.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      ami_patient_cohort AS cohort
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON cohort.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  categorized_troponin AS (
    SELECT
      subject_id,
      hadm_id,
      valuenum,
      CASE
        WHEN valuenum <= 0.01 THEN 'Normal'
        WHEN valuenum > 0.01 AND valuenum <= 0.04 THEN 'Borderline'
        WHEN valuenum > 0.04 THEN 'Elevated'
        ELSE 'Unknown'
      END AS troponin_category
    FROM
      initial_troponin_t
    WHERE
      rn = 1
  )
SELECT
  troponin_category,
  COUNT(DISTINCT subject_id) AS patient_count,
  ROUND(
    100 * COUNT(DISTINCT subject_id) / (
      SELECT COUNT(DISTINCT subject_id) FROM categorized_troponin
    ),
    2
  ) AS percentage_of_patients,
  ROUND(AVG(valuenum), 4) AS avg_troponin_t_ng_ml,
  MIN(valuenum) AS min_troponin_t_ng_ml,
  MAX(valuenum) AS max_troponin_t_ng_ml
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
