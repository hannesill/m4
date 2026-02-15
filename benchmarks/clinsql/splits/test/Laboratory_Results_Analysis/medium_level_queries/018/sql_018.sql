WITH
  acs_patient_admissions AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 90 AND 100
      AND a.dischtime IS NOT NULL
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
        OR (d.icd_version = 10 AND (
            d.icd_code LIKE 'I200%'
            OR d.icd_code LIKE 'I21%'
            OR d.icd_code LIKE 'I22%'
            OR d.icd_code LIKE 'I24%'
          )
        )
      )
  ),
  first_troponin AS (
    SELECT
      acs.hadm_id,
      acs.admittime,
      acs.dischtime,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      acs_patient_admissions AS acs
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON acs.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  ),
  categorized_admissions AS (
    SELECT
      hadm_id,
      DATETIME_DIFF(dischtime, admittime, DAY) AS length_of_stay_days,
      CASE
        WHEN valuenum <= 0.04
        THEN 'Normal'
        WHEN valuenum > 0.04 AND valuenum <= 0.1
        THEN 'Borderline'
        WHEN valuenum > 0.1
        THEN 'Elevated'
        ELSE NULL
      END AS troponin_category
    FROM
      first_troponin
    WHERE
      rn = 1
  )
SELECT
  troponin_category,
  COUNT(hadm_id) AS patient_admission_count,
  ROUND(100.0 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER (), 2) AS percentage_of_total,
  ROUND(AVG(length_of_stay_days), 2) AS avg_length_of_stay_days
FROM
  categorized_admissions
WHERE
  troponin_category IS NOT NULL
GROUP BY
  troponin_category
ORDER BY
  CASE
    WHEN troponin_category = 'Normal' THEN 1
    WHEN troponin_category = 'Borderline' THEN 2
    WHEN troponin_category = 'Elevated' THEN 3
  END;
