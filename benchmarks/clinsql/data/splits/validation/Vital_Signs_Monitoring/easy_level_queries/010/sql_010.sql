WITH MaxDbpPerStay AS (
  SELECT
      ce.stay_id,
      MAX(ce.valuenum) AS max_dbp_per_stay
  FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
  JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON ce.subject_id = p.subject_id
  WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 71 AND 81
      AND ce.itemid IN (220051, 8368)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 30 AND 150
  GROUP BY
      ce.stay_id
)
SELECT
    ROUND(APPROX_QUANTILES(max_dbp_per_stay, 2)[OFFSET(1)], 2) AS median_of_max_dbp
FROM MaxDbpPerStay;
