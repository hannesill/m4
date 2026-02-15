WITH acs_admissions AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 68 AND 78
    AND (
      (
        d.icd_version = 9
        AND (
          d.icd_code LIKE '410%'
          OR d.icd_code = '4111'
        )
      )
      OR
      (
        d.icd_version = 10
        AND (
          d.icd_code LIKE 'I200%'
          OR d.icd_code LIKE 'I21%'
          OR d.icd_code LIKE 'I22%'
          OR d.icd_code LIKE 'I240%'
          OR d.icd_code LIKE 'I248%'
          OR d.icd_code LIKE 'I249%'
        )
      )
    )
),
initial_troponin AS (
  SELECT
    hadm_id,
    valuenum
  FROM
    (
      SELECT
        hadm_id,
        valuenum,
        ROW_NUMBER() OVER (
          PARTITION BY
            hadm_id
          ORDER BY
            charttime ASC
        ) AS rn
      FROM
        `physionet-data.mimiciv_3_1_hosp.labevents`
      WHERE
        itemid = 50911
        AND valuenum IS NOT NULL
        AND valuenum >= 0
    ) AS ranked_labs
  WHERE
    rn = 1
),
final_cohort AS (
  SELECT
    acs.subject_id,
    acs.hadm_id,
    it.valuenum AS initial_troponin_i
  FROM
    acs_admissions AS acs
    INNER JOIN initial_troponin AS it ON acs.hadm_id = it.hadm_id
  WHERE
    it.valuenum > 0.04
)
SELECT
  'Female patients aged 68-78 with ACS and elevated initial Troponin I' AS cohort_description,
  COUNT(DISTINCT subject_id) AS number_of_patients,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(AVG(initial_troponin_i), 3) AS mean_initial_troponin_i,
  ROUND(STDDEV(initial_troponin_i), 3) AS stddev_initial_troponin_i,
  ROUND(MIN(initial_troponin_i), 3) AS min_initial_troponin_i,
  ROUND(MAX(initial_troponin_i), 3) AS max_initial_troponin_i
FROM
  final_cohort;
