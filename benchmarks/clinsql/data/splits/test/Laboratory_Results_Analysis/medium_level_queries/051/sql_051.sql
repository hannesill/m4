WITH
  acs_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 80 AND 90
      AND a.dischtime IS NOT NULL
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
        OR
        (d.icd_version = 10 AND (d.icd_code LIKE 'I200%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%'))
      )
  ),
  first_troponin AS (
    SELECT
      c.hadm_id,
      c.los_days,
      le.valuenum,
      ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      acs_cohort AS c
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
      ft.hadm_id,
      ft.los_days,
      CASE
        WHEN ft.valuenum <= 0.014 THEN 'Normal'
        WHEN ft.valuenum > 0.014 AND ft.valuenum <= 0.1 THEN 'Borderline'
        WHEN ft.valuenum > 0.1 THEN 'Myocardial Injury'
        ELSE 'Unknown'
      END AS troponin_category
    FROM
      first_troponin AS ft
    WHERE
      ft.rn = 1
  )
SELECT
  ct.troponin_category,
  COUNT(ct.hadm_id) AS patient_admission_count,
  ROUND(
    (COUNT(ct.hadm_id) * 100.0) / SUM(COUNT(ct.hadm_id)) OVER(),
    2
  ) AS percentage_of_patients,
  ROUND(AVG(ct.los_days), 1) AS avg_length_of_stay_days
FROM
  categorized_troponin AS ct
WHERE
  ct.troponin_category != 'Unknown'
GROUP BY
  ct.troponin_category
ORDER BY
  CASE
    WHEN ct.troponin_category = 'Normal' THEN 1
    WHEN ct.troponin_category = 'Borderline' THEN 2
    WHEN ct.troponin_category = 'Myocardial Injury' THEN 3
  END;
