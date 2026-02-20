WITH
  acs_admissions AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 84 AND 94
      AND (
        (d.icd_version = 9 AND (
          STARTS_WITH(d.icd_code, '410')
          OR d.icd_code = '4111'
        ))
        OR (d.icd_version = 10 AND (
          STARTS_WITH(d.icd_code, 'I21')
          OR STARTS_WITH(d.icd_code, 'I22')
          OR d.icd_code = 'I200'
        ))
      )
  ),
  initial_troponin AS (
    SELECT
      hadm_id,
      valuenum AS initial_troponin_i,
      ROW_NUMBER() OVER(PARTITION BY hadm_id ORDER BY charttime ASC) AS rn
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents`
    WHERE
      itemid = 50911
      AND valuenum IS NOT NULL
      AND valuenum > 0
  ),
  troponin_uln AS (
    SELECT
      APPROX_QUANTILES(initial_troponin_i, 100)[OFFSET(99)] AS uln_99th_percentile
    FROM
      initial_troponin
    WHERE
      rn = 1
  ),
  final_cohort AS (
    SELECT
      acs.subject_id,
      acs.hadm_id,
      it.initial_troponin_i
    FROM
      acs_admissions AS acs
    INNER JOIN
      initial_troponin AS it
      ON acs.hadm_id = it.hadm_id
    CROSS JOIN
      troponin_uln
    WHERE
      it.rn = 1
      AND it.initial_troponin_i > troponin_uln.uln_99th_percentile
  )
SELECT
  'Female patients aged 84-94 with ACS and initial Troponin I > 99th percentile' AS cohort_description,
  COUNT(DISTINCT subject_id) AS patient_count,
  COUNT(hadm_id) AS admission_count,
  ROUND(AVG(initial_troponin_i), 2) AS mean_troponin_i,
  ROUND(APPROX_QUANTILES(initial_troponin_i, 100)[OFFSET(50)], 2) AS median_troponin_i,
  ROUND(APPROX_QUANTILES(initial_troponin_i, 100)[OFFSET(25)], 2) AS p25_troponin_i,
  ROUND(APPROX_QUANTILES(initial_troponin_i, 100)[OFFSET(75)], 2) AS p75_troponin_i,
  ROUND(
    (APPROX_QUANTILES(initial_troponin_i, 100)[OFFSET(75)] - APPROX_QUANTILES(initial_troponin_i, 100)[OFFSET(25)]), 2
  ) AS iqr_troponin_i,
  ROUND(MIN(initial_troponin_i), 2) AS min_troponin_i_in_cohort,
  ROUND(MAX(initial_troponin_i), 2) AS max_troponin_i_in_cohort
FROM
  final_cohort;
