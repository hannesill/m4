WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) BETWEEN 42 AND 52
      AND a.admittime IS NOT NULL
  ),
  first_troponin AS (
    SELECT
      pc.subject_id,
      le.valuenum,
      ROW_NUMBER() OVER (
        PARTITION BY
          pc.subject_id,
          pc.hadm_id
        ORDER BY
          le.charttime ASC
      ) AS measurement_rank
    FROM
      patient_cohort AS pc
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON pc.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  categorized_troponin AS (
    SELECT
      subject_id,
      valuenum,
      CASE
        WHEN valuenum < 0.014 THEN 'Normal'
        WHEN valuenum >= 0.014
        AND valuenum < 0.04 THEN 'Borderline'
        WHEN valuenum >= 0.04 THEN 'Myocardial Injury'
        ELSE 'Unknown'
      END AS troponin_category
    FROM
      first_troponin
    WHERE
      measurement_rank = 1
  )
SELECT
  troponin_category,
  COUNT(DISTINCT subject_id) AS patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT subject_id) / SUM(COUNT(DISTINCT subject_id)) OVER (),
    2
  ) AS percentage_of_patients
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
