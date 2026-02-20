WITH
  ami_admissions AS (
    SELECT DISTINCT
      hadm_id,
      subject_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      SUBSTR(icd_code, 1, 3) IN ('410', 'I21') AND icd_version IN (9, 10)
  ),
  target_patient_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      ami_admissions AS ami
      ON a.hadm_id = ami.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 49 AND 59
  ),
  initial_troponin AS (
    SELECT
      hadm_id,
      valuenum,
      ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY charttime ASC) AS measurement_rank
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents`
    WHERE
      itemid = 51003
      AND valuenum IS NOT NULL
      AND hadm_id IN (
        SELECT hadm_id FROM target_patient_admissions
      )
  ),
  final_cohort AS (
    SELECT
      it.hadm_id,
      it.valuenum AS initial_troponin_value
    FROM
      initial_troponin AS it
    WHERE
      it.measurement_rank = 1
      AND it.valuenum > 0.04
  )
SELECT
  'Male patients, aged 49-59, with AMI and initial Troponin > 0.04 ng/mL' AS cohort_description,
  COUNT(hadm_id) AS number_of_admissions,
  ROUND(APPROX_QUANTILES(initial_troponin_value, 100)[OFFSET(50)], 3) AS median_troponin_value,
  ROUND(APPROX_QUANTILES(initial_troponin_value, 100)[OFFSET(25)], 3) AS p25_troponin_value,
  ROUND(APPROX_QUANTILES(initial_troponin_value, 100)[OFFSET(75)], 3) AS p75_troponin_value,
  ROUND(
    (
      APPROX_QUANTILES(initial_troponin_value, 100)[OFFSET(75)] - APPROX_QUANTILES(initial_troponin_value, 100)[OFFSET(25)]
    ),
    3
  ) AS iqr_troponin_value
FROM
  final_cohort;
