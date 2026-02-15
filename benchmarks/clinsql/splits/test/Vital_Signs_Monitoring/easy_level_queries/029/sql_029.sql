WITH FirstSpO2 AS (
  SELECT
    ce.subject_id,
    ce.valuenum,
    ROW_NUMBER() OVER(PARTITION BY ce.subject_id ORDER BY ce.charttime ASC) as rn
  FROM `physionet-data.mimiciv_3_1_icu.chartevents` ce
  WHERE
    ce.itemid IN (220277, 646)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 70 AND 100
),
PatientCohort AS (
  SELECT
    f.valuenum
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN FirstSpO2 f ON p.subject_id = f.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 62 AND 72
    AND f.rn = 1
)
SELECT
  ROUND(
    (APPROX_QUANTILES(valuenum, 4)[OFFSET(3)])
    - (APPROX_QUANTILES(valuenum, 4)[OFFSET(1)])
  , 2) AS iqr_spo2
FROM PatientCohort;
