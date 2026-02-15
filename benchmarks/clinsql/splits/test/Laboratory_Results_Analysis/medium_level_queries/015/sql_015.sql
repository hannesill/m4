WITH
  acs_admissions AS (
    SELECT DISTINCT
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 88 AND 98
      AND (
        (d.icd_version = 9 AND (
          d.icd_code LIKE '410%'
          OR d.icd_code = '4111'
        ))
        OR
        (d.icd_version = 10 AND (
          d.icd_code LIKE 'I20.0%'
          OR d.icd_code LIKE 'I21%'
          OR d.icd_code LIKE 'I22%'
          OR d.icd_code LIKE 'I24.0%'
          OR d.icd_code LIKE 'I24.8%'
          OR d.icd_code LIKE 'I24.9%'
        ))
      )
  ),
  initial_troponin AS (
    SELECT
      acs.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
    FROM
      acs_admissions AS acs
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON acs.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum > 0
  ),
  elevated_initial_troponin AS (
    SELECT
      it.hadm_id,
      it.valuenum
    FROM
      initial_troponin AS it
    WHERE
      it.rn = 1
      AND it.valuenum > 0.01
  )
SELECT
  'Female patients, aged 88-98, with ACS and initial elevated Troponin T' AS cohort_description,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(50)], 3) AS median_troponin_t_ng_ml,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3) AS p25_troponin_t_ng_ml,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)], 3) AS p75_troponin_t_ng_ml,
  ROUND(
    (APPROX_QUANTILES(valuenum, 100)[OFFSET(75)] - APPROX_QUANTILES(valuenum, 100)[OFFSET(25)]),
    3
  ) AS iqr_troponin_t_ng_ml,
  ROUND(AVG(valuenum), 3) AS mean_troponin_t_ng_ml,
  ROUND(MIN(valuenum), 3) AS min_elevated_troponin_t_ng_ml,
  ROUND(MAX(valuenum), 3) AS max_elevated_troponin_t_ng_ml
FROM
  elevated_initial_troponin;
