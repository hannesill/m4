WITH PerStayMAP AS (
  SELECT
    ce.stay_id,
    AVG(ce.valuenum) AS avg_map_per_stay
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 73 AND 83
    AND ce.itemid IN (
      220052,
      456
    )
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 40 AND 140
  GROUP BY
    ce.stay_id
)
SELECT
  ROUND(AVG(avg_map_per_stay), 2) AS avg_of_mean_map_per_stay
FROM PerStayMAP;
