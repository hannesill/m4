WITH patient_cohort AS (
  SELECT DISTINCT
    a.subject_id,
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
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 87 AND 97
    AND (
      (d.icd_version = 9 AND d.icd_code LIKE '7865%')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'R07%')
    )
    AND a.admittime IS NOT NULL
),
first_troponin AS (
  SELECT
    c.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY c.hadm_id ORDER BY le.charttime ASC) as rn
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
    valuenum AS troponin_value,
    CASE
      WHEN valuenum <= 0.04 THEN 'Normal'
      WHEN valuenum > 0.04 AND valuenum <= 0.1 THEN 'Borderline'
      WHEN valuenum > 0.1 THEN 'Myocardial Injury'
      ELSE 'Unknown'
    END AS troponin_category
  FROM
    first_troponin
  WHERE
    rn = 1
)
SELECT
  troponin_category,
  COUNT(hadm_id) AS admission_count,
  ROUND(100.0 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER(), 2) AS percentage_of_total,
  ROUND(AVG(troponin_value), 4) AS mean_troponin,
  ROUND(APPROX_QUANTILES(troponin_value, 100)[OFFSET(50)], 4) AS median_troponin,
  ROUND(APPROX_QUANTILES(troponin_value, 100)[OFFSET(25)], 4) AS p25_troponin,
  ROUND(APPROX_QUANTILES(troponin_value, 100)[OFFSET(75)], 4) AS p75_troponin,
  ROUND(
    (APPROX_QUANTILES(troponin_value, 100)[OFFSET(75)] - APPROX_QUANTILES(troponin_value, 100)[OFFSET(25)]),
    4
  ) AS iqr_troponin
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
    WHEN troponin_category = 'Myocardial Injury' THEN 3
  END;
