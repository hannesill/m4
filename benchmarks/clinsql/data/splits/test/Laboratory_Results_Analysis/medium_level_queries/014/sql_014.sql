WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND a.admittime IS NOT NULL
  ),
  acs_admissions AS (
    SELECT DISTINCT
      pc.hadm_id
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON pc.hadm_id = dx.hadm_id
    WHERE
      pc.age_at_admission BETWEEN 79 AND 89
      AND (
        (dx.icd_version = 9 AND (
            STARTS_WITH(dx.icd_code, '410')
            OR dx.icd_code = '4111'
        ))
        OR
        (dx.icd_version = 10 AND (
            STARTS_WITH(dx.icd_code, 'I21')
            OR STARTS_WITH(dx.icd_code, 'I22')
            OR dx.icd_code = 'I200'
        ))
      )
  ),
  initial_troponin_t AS (
    SELECT
      acs.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER(PARTITION BY acs.hadm_id ORDER BY le.charttime ASC) AS measurement_rank
    FROM
      acs_admissions AS acs
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON acs.hadm_id = le.hadm_id
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
      initial_troponin_t
    WHERE
      measurement_rank = 1
  )
SELECT
  troponin_category,
  COUNT(hadm_id) AS patient_count,
  ROUND(
    100 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER(),
    2
  ) AS percentage_of_total
FROM
  categorized_troponin
GROUP BY
  troponin_category
ORDER BY
  CASE
    WHEN troponin_category = 'Normal' THEN 1
    WHEN troponin_category = 'Borderline' THEN 2
    WHEN troponin_category = 'Elevated' THEN 3
    ELSE 4
  END;
