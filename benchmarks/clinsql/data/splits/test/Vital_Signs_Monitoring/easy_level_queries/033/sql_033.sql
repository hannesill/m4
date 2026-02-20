WITH HeartRateData AS (
  SELECT
    ce.valuenum
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON p.subject_id = icu.subject_id
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON icu.stay_id = ce.stay_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 45 AND 55
    AND ce.itemid IN (220045, 211)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 30 AND 200
    AND DATETIME_DIFF(ce.charttime, icu.intime, HOUR) >= 24
)
SELECT
  ROUND(
    (APPROX_QUANTILES(valuenum, 4)[OFFSET(3)] - APPROX_QUANTILES(valuenum, 4)[OFFSET(1)]),
    2
  ) AS heart_rate_iqr
FROM HeartRateData
