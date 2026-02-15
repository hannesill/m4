WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM ie.intime) - p.anchor_year) BETWEEN 48 AND 58
      AND ie.intime IS NOT NULL
  ),
  avg_hr_first_48h AS (
    SELECT
      pc.subject_id,
      pc.hadm_id,
      pc.stay_id,
      AVG(ce.valuenum) AS avg_hr
    FROM
      patient_cohort AS pc
      INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220045, 211)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
      AND DATETIME_DIFF(ce.charttime, pc.intime, HOUR) BETWEEN 0 AND 48
    GROUP BY
      pc.subject_id,
      pc.hadm_id,
      pc.stay_id
  ),
  aki_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND SUBSTR(icd_code, 1, 3) = '584'
      )
      OR (
        icd_version = 10
        AND SUBSTR(icd_code, 1, 3) = 'N17'
      )
  ),
  combined_data AS (
    SELECT
      hr.subject_id,
      hr.hadm_id,
      CASE
        WHEN aki.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS has_aki,
      CASE
        WHEN hr.avg_hr < 60 THEN '< 60'
        WHEN hr.avg_hr >= 60 AND hr.avg_hr < 100 THEN '60 - 99'
        WHEN hr.avg_hr >= 100 AND hr.avg_hr < 120 THEN '100 - 119'
        WHEN hr.avg_hr >= 120 THEN '>= 120'
        ELSE 'Unknown'
      END AS hr_category
    FROM
      avg_hr_first_48h AS hr
      LEFT JOIN aki_diagnoses AS aki ON hr.hadm_id = aki.hadm_id
  )
SELECT
  hr_category,
  COUNT(DISTINCT subject_id) AS patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT subject_id) / SUM(COUNT(DISTINCT subject_id)) OVER (),
    2
  ) AS percent_of_total_patients,
  ROUND(
    100.0 * COUNT(DISTINCT CASE WHEN has_aki = 1 THEN subject_id END) / COUNT(DISTINCT subject_id),
    2
  ) AS aki_rate_percent
FROM
  combined_data
WHERE
  hr_category != 'Unknown'
GROUP BY
  hr_category
ORDER BY
  CASE
    WHEN hr_category = '< 60' THEN 1
    WHEN hr_category = '60 - 99' THEN 2
    WHEN hr_category = '100 - 119' THEN 3
    WHEN hr_category = '>= 120' THEN 4
  END;
