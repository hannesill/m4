WITH
  ami_patient_cohort AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) BETWEEN 77 AND 87
      AND (
        (
          d.icd_version = 9
          AND d.icd_code LIKE '410%'
        )
        OR (
          d.icd_version = 10
          AND d.icd_code LIKE 'I21%'
        )
      )
  ),
  initial_troponin AS (
    SELECT
      cohort.hadm_id,
      le.valuenum,
      CASE
        WHEN le.valuenum < 0.014
        THEN 'Normal (< 0.014 ng/mL)'
        WHEN le.valuenum >= 0.014 AND le.valuenum <= 0.052
        THEN 'Borderline (0.014-0.052 ng/mL)'
        WHEN le.valuenum > 0.052
        THEN 'Myocardial Injury (> 0.052 ng/mL)'
        ELSE 'Unknown'
      END AS troponin_category,
      ROW_NUMBER() OVER (
        PARTITION BY
          cohort.hadm_id
        ORDER BY
          le.charttime ASC
      ) AS measurement_rank
    FROM
      ami_patient_cohort AS cohort
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON cohort.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= 0
  )
SELECT
  troponin_category,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(
    100.0 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER (),
    2
  ) AS percentage_of_cohort
FROM
  initial_troponin
WHERE
  measurement_rank = 1
  AND troponin_category != 'Unknown'
GROUP BY
  troponin_category
ORDER BY
  CASE
    WHEN troponin_category LIKE 'Normal%'
    THEN 1
    WHEN troponin_category LIKE 'Borderline%'
    THEN 2
    WHEN troponin_category LIKE 'Myocardial Injury%'
    THEN 3
  END;
