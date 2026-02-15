WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      i.stay_id,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS i
      ON a.hadm_id = i.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 41 AND 51
  ),
  stroke_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '430' AND '438')
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'I60' AND 'I69')
  ),
  map_measurements AS (
    SELECT
      pc.subject_id,
      pc.hadm_id,
      CASE
        WHEN ce.valuenum < 65 THEN '< 65'
        WHEN ce.valuenum >= 65 AND ce.valuenum < 75 THEN '65 - 74'
        WHEN ce.valuenum >= 75 AND ce.valuenum < 85 THEN '75 - 84'
        WHEN ce.valuenum >= 85 THEN '>= 85'
        ELSE NULL
      END AS map_category
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220052, 52)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0 AND ce.valuenum < 300
  ),
  patient_categories_with_stroke AS (
    SELECT DISTINCT
      m.subject_id,
      m.hadm_id,
      m.map_category,
      CASE
        WHEN s.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS has_stroke
    FROM
      map_measurements AS m
    LEFT JOIN
      stroke_diagnoses AS s
      ON m.hadm_id = s.hadm_id
    WHERE
      m.map_category IS NOT NULL
  )
SELECT
  pcs.map_category,
  COUNT(DISTINCT pcs.subject_id) AS patient_count,
  COUNT(DISTINCT CASE WHEN pcs.has_stroke = 1 THEN pcs.subject_id END) AS stroke_patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT CASE WHEN pcs.has_stroke = 1 THEN pcs.subject_id END)
    / COUNT(DISTINCT pcs.subject_id),
    2
  ) AS stroke_rate_percent
FROM
  patient_categories_with_stroke AS pcs
GROUP BY
  pcs.map_category
ORDER BY
  CASE
    WHEN pcs.map_category = '< 65' THEN 1
    WHEN pcs.map_category = '65 - 74' THEN 2
    WHEN pcs.map_category = '75 - 84' THEN 3
    WHEN pcs.map_category = '>= 85' THEN 4
  END;
