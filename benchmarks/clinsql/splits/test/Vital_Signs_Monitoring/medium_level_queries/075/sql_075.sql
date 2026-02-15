WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
      ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 56 AND 66
  ),
  avg_map_per_stay AS (
    SELECT
      pc.stay_id,
      pc.subject_id,
      pc.hadm_id,
      AVG(ce.valuenum) AS average_map
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (
        220052,
        456,
        225312
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0 AND ce.valuenum < 300
    GROUP BY
      pc.stay_id,
      pc.subject_id,
      pc.hadm_id
  ),
  stroke_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432', '433', '434', '436')
      )
      OR
      (
        icd_version = 10 AND (
          STARTS_WITH(icd_code, 'I60')
          OR STARTS_WITH(icd_code, 'I61')
          OR STARTS_WITH(icd_code, 'I62')
          OR STARTS_WITH(icd_code, 'I63')
          OR STARTS_WITH(icd_code, 'I64')
        )
      )
  ),
  categorized_stays AS (
    SELECT
      map.subject_id,
      map.hadm_id,
      CASE
        WHEN sd.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS had_stroke,
      CASE
        WHEN map.average_map < 65
        THEN '< 65 mmHg'
        WHEN map.average_map >= 65 AND map.average_map < 75
        THEN '65 - 74 mmHg'
        WHEN map.average_map >= 75 AND map.average_map < 85
        THEN '75 - 84 mmHg'
        WHEN map.average_map >= 85
        THEN '>= 85 mmHg'
        ELSE 'Unknown'
      END AS map_category
    FROM
      avg_map_per_stay AS map
    LEFT JOIN
      stroke_diagnoses AS sd
      ON map.hadm_id = sd.hadm_id
  )
SELECT
  cs.map_category,
  COUNT(DISTINCT cs.subject_id) AS patient_count,
  SUM(cs.had_stroke) AS stroke_count,
  ROUND(100.0 * SUM(cs.had_stroke) / COUNT(DISTINCT cs.subject_id), 2) AS stroke_rate_percent
FROM
  categorized_stays AS cs
WHERE
  cs.map_category != 'Unknown'
GROUP BY
  cs.map_category
ORDER BY
  CASE
    WHEN cs.map_category = '< 65 mmHg' THEN 1
    WHEN cs.map_category = '65 - 74 mmHg' THEN 2
    WHEN cs.map_category = '75 - 84 mmHg' THEN 3
    WHEN cs.map_category = '>= 85 mmHg' THEN 4
  END;
