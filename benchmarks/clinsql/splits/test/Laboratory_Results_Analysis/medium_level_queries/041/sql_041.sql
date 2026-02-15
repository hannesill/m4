WITH
  acs_patients AS (
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
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 43 AND 53
      AND (
        (d.icd_version = 9 AND (STARTS_WITH(d.icd_code, '410') OR d.icd_code = '4111'))
        OR (d.icd_version = 10 AND (STARTS_WITH(d.icd_code, 'I21') OR d.icd_code = 'I200'))
      )
  ),
  initial_troponin AS (
    SELECT
      ap.hadm_id,
      le.valuenum,
      ROW_NUMBER() OVER (PARTITION BY ap.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      acs_patients AS ap
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON ap.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
      AND le.valuenum > 0
  ),
  elevated_initial_troponin AS (
    SELECT
      it.valuenum
    FROM
      initial_troponin AS it
    WHERE
      it.rn = 1
      AND it.valuenum > 0.014
  )
SELECT
  COUNT(*) AS number_of_patients_in_cohort,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3) AS p25_troponin_t_ng_mL,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(50)], 3) AS median_troponin_t_ng_mL,
  ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)], 3) AS p75_troponin_t_ng_mL,
  ROUND(
    APPROX_QUANTILES(valuenum, 100)[OFFSET(75)] - APPROX_QUANTILES(valuenum, 100)[OFFSET(25)],
    3
  ) AS iqr_troponin_t_ng_mL,
  ROUND(AVG(valuenum), 3) AS avg_troponin_t_ng_mL,
  ROUND(MIN(valuenum), 3) AS min_troponin_t_ng_mL,
  ROUND(MAX(valuenum), 3) AS max_troponin_t_ng_mL
FROM
  elevated_initial_troponin;
