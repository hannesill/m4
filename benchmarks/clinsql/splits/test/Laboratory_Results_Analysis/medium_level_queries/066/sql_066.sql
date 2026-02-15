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
      AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
  ),
  chest_pain_admissions AS (
    SELECT DISTINCT
      pc.hadm_id
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON pc.hadm_id = d.hadm_id
    WHERE
      pc.admission_age BETWEEN 39 AND 49
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '786.5%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'R07%')
      )
  ),
  initial_troponin AS (
    SELECT
      hadm_id,
      valuenum AS troponin_t_value
    FROM
      (
        SELECT
          le.hadm_id,
          le.valuenum,
          ROW_NUMBER() OVER (PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
        FROM
          `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        INNER JOIN
          chest_pain_admissions AS cpa
          ON le.hadm_id = cpa.hadm_id
        WHERE
          le.itemid = 51003
          AND le.valuenum IS NOT NULL
          AND le.valuenum >= 0
      ) AS ranked_labs
    WHERE
      rn = 1
  ),
  categorized_troponin AS (
    SELECT
      troponin_t_value,
      CASE
        WHEN troponin_t_value < 0.014 THEN 'Normal'
        WHEN troponin_t_value >= 0.014 AND troponin_t_value <= 0.04 THEN 'Borderline'
        WHEN troponin_t_value > 0.04 THEN 'Myocardial Injury'
        ELSE 'Unknown'
      END AS troponin_category
    FROM
      initial_troponin
  )
SELECT
  troponin_category,
  COUNT(troponin_t_value) AS patient_count,
  ROUND(COUNT(troponin_t_value) * 100.0 / (SELECT COUNT(*) FROM categorized_troponin), 2) AS percentage_of_cohort,
  ROUND(AVG(troponin_t_value), 4) AS mean_troponin,
  ROUND(APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(50)], 4) AS median_troponin,
  ROUND(
    (APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(75)] - APPROX_QUANTILES(troponin_t_value, 100)[OFFSET(25)]), 4
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
