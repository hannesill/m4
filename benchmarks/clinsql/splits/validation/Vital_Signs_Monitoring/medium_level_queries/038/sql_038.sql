WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
      ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 66 AND 76
  ),
  ventilated_patients AS (
    SELECT DISTINCT
      pc.stay_id,
      pc.intime
    FROM
      patient_cohort AS pc
    WHERE
      EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        WHERE
          ce.stay_id = pc.stay_id
          AND ce.itemid IN (220339, 223849, 223835, 224685, 224684, 224695)
          AND DATETIME_DIFF(ce.charttime, pc.intime, HOUR) <= 6
      )
  ),
  first_6hr_sbp AS (
    SELECT
      vp.stay_id,
      ce.valuenum AS sbp_value
    FROM
      ventilated_patients AS vp
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON vp.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220050, 51)
      AND ce.valuenum IS NOT NULL
      AND DATETIME_DIFF(ce.charttime, vp.intime, HOUR) BETWEEN 0 AND 6
      AND ce.valuenum BETWEEN 40 AND 250
  )
SELECT
  COUNT(DISTINCT stay_id) AS number_of_patients,
  COUNT(sbp_value) AS number_of_sbp_measurements,
  ROUND(APPROX_QUANTILES(sbp_value, 4)[OFFSET(1)], 1) AS sbp_25th_percentile_q1,
  ROUND(APPROX_QUANTILES(sbp_value, 4)[OFFSET(2)], 1) AS sbp_median_q2,
  ROUND(APPROX_QUANTILES(sbp_value, 4)[OFFSET(3)], 1) AS sbp_75th_percentile_q3,
  ROUND(
    APPROX_QUANTILES(sbp_value, 4)[OFFSET(3)] - APPROX_QUANTILES(sbp_value, 4)[OFFSET(1)],
    1
  ) AS sbp_interquartile_range
FROM
  first_6hr_sbp;
