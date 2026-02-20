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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 88 AND 98
      AND ie.intime IS NOT NULL
  ),
  hfnc_stays AS (
    SELECT DISTINCT
      pc.stay_id,
      pc.intime
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (226732, 227287)
  ),
  gcs_on_day_2_plus AS (
    SELECT
      hs.stay_id,
      ce.valuenum AS gcs_total
    FROM
      hfnc_stays AS hs
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON hs.stay_id = ce.stay_id
    WHERE
      ce.itemid = 226758
      AND DATETIME_DIFF(ce.charttime, hs.intime, HOUR) >= 24
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 3 AND 15
  )
SELECT
  COUNT(DISTINCT stay_id) AS number_of_patients,
  COUNT(gcs_total) AS number_of_gcs_measurements,
  APPROX_QUANTILES(gcs_total, 2)[OFFSET(1)] AS median_gcs_total,
  ROUND(AVG(gcs_total), 2) AS average_gcs_total,
  MIN(gcs_total) AS min_gcs_total,
  MAX(gcs_total) AS max_gcs_total
FROM
  gcs_on_day_2_plus;
