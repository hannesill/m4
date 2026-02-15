WITH patient_cohort AS (
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
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 41 AND 51
    AND (
      d.icd_code LIKE '410%' OR d.icd_code LIKE 'I21%'
      OR d.icd_code IN ('78650', '78659', 'R0789', 'R079')
    )
),
initial_troponin AS (
  SELECT
    pc.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY pc.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON pc.hadm_id = le.hadm_id
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
      WHEN valuenum <= 0.01 THEN 'Normal'
      WHEN valuenum > 0.01 AND valuenum <= 0.04 THEN 'Borderline'
      WHEN valuenum > 0.04 THEN 'Elevated'
      ELSE 'Unknown'
    END AS troponin_category
  FROM
    initial_troponin
  WHERE
    rn = 1
)
SELECT
  troponin_category,
  COUNT(hadm_id) AS admission_count,
  ROUND(COUNT(hadm_id) * 100.0 / SUM(COUNT(hadm_id)) OVER(), 2) AS percentage_of_admissions,
  ROUND(AVG(valuenum), 3) AS mean_troponin_t,
  APPROX_QUANTILES(valuenum, 100)[OFFSET(50)] AS median_troponin_t,
  ROUND(
    APPROX_QUANTILES(valuenum, 100)[OFFSET(75)] - APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3
  ) AS iqr_troponin_t
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
