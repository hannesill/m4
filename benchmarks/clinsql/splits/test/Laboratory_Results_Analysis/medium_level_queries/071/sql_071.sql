WITH
  acs_admissions AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND a.dischtime IS NOT NULL
      AND (
        (d.icd_version = 9 AND (
            d.icd_code LIKE '410%'
            OR d.icd_code = '4111'
            OR d.icd_code LIKE '7865%'
        ))
        OR
        (d.icd_version = 10 AND (
            d.icd_code LIKE 'I21%'
            OR d.icd_code = 'I200'
            OR d.icd_code LIKE 'I24%'
            OR d.icd_code LIKE 'R07%'
        ))
      )
  ),
  target_cohort AS (
    SELECT
      hadm_id,
      admittime,
      dischtime
    FROM acs_admissions
    WHERE age_at_admission BETWEEN 43 AND 53
  ),
  initial_troponin AS (
    SELECT
      tc.hadm_id,
      tc.admittime,
      tc.dischtime,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY tc.hadm_id ORDER BY le.charttime) AS measurement_rank
    FROM
      target_cohort AS tc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON tc.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  categorized_results AS (
    SELECT
      hadm_id,
      DATETIME_DIFF(dischtime, admittime, DAY) AS length_of_stay_days,
      CASE
        WHEN valuenum <= 0.04 THEN 'Normal'
        WHEN valuenum > 0.04 AND valuenum <= 0.1 THEN 'Borderline'
        WHEN valuenum > 0.1 THEN 'Elevated'
        ELSE 'Unknown'
      END AS troponin_category
    FROM
      initial_troponin
    WHERE
      measurement_rank = 1
  )
SELECT
  troponin_category,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(100 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER (), 2) AS percentage_of_patients,
  ROUND(AVG(length_of_stay_days), 1) AS avg_length_of_stay_days
FROM
  categorized_results
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
