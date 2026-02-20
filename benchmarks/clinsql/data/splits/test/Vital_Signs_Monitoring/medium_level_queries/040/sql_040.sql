WITH
patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 81 AND 91
),
hiflow_stays AS (
  SELECT DISTINCT
    icu.stay_id
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON pc.hadm_id = icu.hadm_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON icu.stay_id = ce.stay_id
  WHERE
    ce.itemid = 226732
    AND ce.value = 'High flow nasal cannula'
),
sbp_measurements AS (
  SELECT
    hfs.stay_id,
    ce.valuenum AS sbp
  FROM
    hiflow_stays AS hfs
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON hfs.stay_id = ce.stay_id
  WHERE
    ce.itemid IN (220050, 51)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 40 AND 300
),
mean_sbp_per_stay AS (
  SELECT
    stay_id,
    AVG(sbp) AS avg_sbp_per_stay
  FROM
    sbp_measurements
  GROUP BY
    stay_id
)
SELECT
  COUNT(stay_id) AS number_of_matching_stays,
  ROUND(MIN(avg_sbp_per_stay), 2) AS min_of_mean_sbp,
  ROUND(AVG(avg_sbp_per_stay), 2) AS overall_avg_of_mean_sbp,
  ROUND(MAX(avg_sbp_per_stay), 2) AS max_of_mean_sbp,
  ROUND(STDDEV(avg_sbp_per_stay), 2) AS stddev_of_mean_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp_per_stay, 100)[OFFSET(25)], 2) AS p25_mean_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp_per_stay, 100)[OFFSET(50)], 2) AS median_mean_sbp,
  ROUND(APPROX_QUANTILES(avg_sbp_per_stay, 100)[OFFSET(75)], 2) AS p75_mean_sbp
FROM
  mean_sbp_per_stay;
