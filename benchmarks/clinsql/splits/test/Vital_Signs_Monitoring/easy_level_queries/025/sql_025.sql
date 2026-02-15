WITH mean_rr_per_stay AS (
  SELECT
    AVG(ce.valuenum) AS avg_rr
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 39 AND 49
    AND ce.itemid IN (220210, 615)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 5 AND 50
  GROUP BY
    ce.stay_id
)
SELECT
  ROUND(
    APPROX_QUANTILES(avg_rr, 100)[OFFSET(75)],
    2
  ) AS p75_mean_respiratory_rate
FROM mean_rr_per_stay
