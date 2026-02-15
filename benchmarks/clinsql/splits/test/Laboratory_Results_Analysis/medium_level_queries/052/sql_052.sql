WITH ami_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 76 AND 86
    AND EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      WHERE d.hadm_id = a.hadm_id
        AND (
          (d.icd_version = 9 AND d.icd_code LIKE '410%')
          OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
        )
    )
),

first_troponin AS (
  SELECT
    c.hadm_id,
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY c.hadm_id ORDER BY le.charttime ASC) as rn
  FROM
    ami_cohort AS c
  JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON c.hadm_id = le.hadm_id
  WHERE
    le.itemid = 50911
    AND le.valuenum IS NOT NULL
    AND le.valuenum >= 0
),

categorized_troponin AS (
  SELECT
    hadm_id,
    valuenum AS troponin_i_value,
    CASE
      WHEN valuenum <= 0.04 THEN 'Normal'
      WHEN valuenum > 0.04 AND valuenum < 0.40 THEN 'Borderline'
      WHEN valuenum >= 0.40 THEN 'Elevated (MI Likely)'
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
  ROUND(COUNT(hadm_id) * 100.0 / SUM(COUNT(hadm_id)) OVER(), 2) AS percentage_of_patients,
  ROUND(AVG(troponin_i_value), 3) AS mean_troponin,
  APPROX_QUANTILES(troponin_i_value, 100)[OFFSET(50)] AS median_troponin,
  APPROX_QUANTILES(troponin_i_value, 100)[OFFSET(25)] AS p25_troponin,
  APPROX_QUANTILES(troponin_i_value, 100)[OFFSET(75)] AS p75_troponin
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
    WHEN troponin_category = 'Elevated (MI Likely)' THEN 3
  END;
