WITH mean_temp_per_stay AS (
  SELECT
    ce.stay_id,
    AVG(ce.valuenum) AS avg_temp
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 37 AND 47
    AND ce.itemid IN (223762, 676)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 95 AND 110
  GROUP BY
    ce.stay_id
)
SELECT
  ROUND(
    APPROX_QUANTILES(avg_temp, 100)[OFFSET(75)],
    2
  ) AS p75_mean_temperature
FROM mean_temp_per_stay;
