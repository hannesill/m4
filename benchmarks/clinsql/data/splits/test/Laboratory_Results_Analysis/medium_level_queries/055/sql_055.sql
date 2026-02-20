WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
  ),
  admissions_with_condition AS (
    SELECT DISTINCT
      pc.subject_id,
      pc.hadm_id,
      pc.admittime,
      pc.dischtime
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON pc.hadm_id = d.hadm_id
    WHERE
      pc.age_at_admission BETWEEN 81 AND 91
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code IN ('78650', '78651', '78659')))
        OR
        (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code IN ('R079', 'R0789', 'R072')))
      )
  ),
  first_troponin AS (
    SELECT
      ac.hadm_id,
      ac.admittime,
      ac.dischtime,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      admissions_with_condition AS ac
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON ac.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
      AND le.charttime BETWEEN DATETIME_SUB(ac.admittime, INTERVAL 6 HOUR) AND ac.dischtime
  ),
  categorized_patients AS (
    SELECT
      ft.hadm_id,
      CASE
        WHEN ft.valuenum < 0.014 THEN 'Normal'
        WHEN ft.valuenum >= 0.014 AND ft.valuenum < 0.04 THEN 'Borderline'
        WHEN ft.valuenum >= 0.04 THEN 'Myocardial Injury'
        ELSE 'Unknown'
      END AS troponin_category,
      DATETIME_DIFF(ft.dischtime, ft.admittime, DAY) AS length_of_stay_days
    FROM
      first_troponin AS ft
    WHERE
      ft.rn = 1
  )
SELECT
  cp.troponin_category,
  COUNT(cp.hadm_id) AS patient_count,
  ROUND(100 * COUNT(cp.hadm_id) / SUM(COUNT(cp.hadm_id)) OVER (), 2) AS percentage_of_patients,
  ROUND(AVG(cp.length_of_stay_days), 1) AS avg_length_of_stay_days
FROM
  categorized_patients AS cp
WHERE
  cp.troponin_category != 'Unknown'
GROUP BY
  cp.troponin_category
ORDER BY
  CASE
    WHEN cp.troponin_category = 'Normal' THEN 1
    WHEN cp.troponin_category = 'Borderline' THEN 2
    WHEN cp.troponin_category = 'Myocardial Injury' THEN 3
  END;
