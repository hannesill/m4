WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime,
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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 70 AND 80
      AND ie.intime IS NOT NULL
  ),
  first_24hr_sbp AS (
    SELECT
      cohort.subject_id,
      cohort.hadm_id,
      cohort.stay_id,
      ce.valuenum AS sbp_value
    FROM
      patient_cohort AS cohort
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON cohort.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (
        220050,
        51
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0 AND ce.valuenum < 300
      AND DATETIME_DIFF(ce.charttime, cohort.intime, HOUR) BETWEEN 0 AND 24
  ),
  patient_sbp_category AS (
    SELECT
      subject_id,
      hadm_id,
      stay_id,
      CASE
        WHEN MAX(sbp_value) < 130 THEN '<130'
        WHEN MAX(sbp_value) >= 130 AND MAX(sbp_value) <= 139 THEN '130-139'
        WHEN MAX(sbp_value) >= 140 AND MAX(sbp_value) <= 159 THEN '140-159'
        WHEN MAX(sbp_value) >= 160 THEN '>=160'
        ELSE NULL
      END AS sbp_category
    FROM
      first_24hr_sbp
    GROUP BY
      subject_id,
      hadm_id,
      stay_id
  ),
  stroke_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '433', '434', '436')
      )
      OR (
        icd_version = 10
        AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62', 'I63')
      )
  )
SELECT
  p_cat.sbp_category,
  COUNT(DISTINCT p_cat.subject_id) AS number_of_patients,
  ROUND(
    100.0 * COUNT(DISTINCT p_cat.subject_id) / SUM(COUNT(DISTINCT p_cat.subject_id)) OVER (),
    2
  ) AS percent_of_total_patients,
  COUNT(DISTINCT CASE WHEN s.hadm_id IS NOT NULL THEN p_cat.subject_id END) AS stroke_patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT CASE WHEN s.hadm_id IS NOT NULL THEN p_cat.subject_id END) / COUNT(DISTINCT p_cat.subject_id),
    2
  ) AS stroke_rate_percent
FROM
  patient_sbp_category AS p_cat
LEFT JOIN
  stroke_diagnoses AS s
  ON p_cat.hadm_id = s.hadm_id
WHERE
  p_cat.sbp_category IS NOT NULL
GROUP BY
  p_cat.sbp_category
ORDER BY
  CASE
    WHEN p_cat.sbp_category = '<130' THEN 1
    WHEN p_cat.sbp_category = '130-139' THEN 2
    WHEN p_cat.sbp_category = '140-159' THEN 3
    WHEN p_cat.sbp_category = '>=160' THEN 4
  END;
