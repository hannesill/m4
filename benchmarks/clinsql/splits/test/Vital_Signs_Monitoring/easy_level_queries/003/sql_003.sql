WITH MeanHeartRatePerStay AS (
  SELECT
    ce.stay_id,
    AVG(ce.valuenum) AS mean_hr
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 40 AND 50
    AND ce.itemid IN (220045, 211)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 30 AND 200
  GROUP BY
    ce.stay_id
)
SELECT
  ROUND(
    APPROX_QUANTILES(mhr.mean_hr, 2)[OFFSET(1)],
    2
  ) AS median_of_mean_heart_rate
FROM MeanHeartRatePerStay mhr;
