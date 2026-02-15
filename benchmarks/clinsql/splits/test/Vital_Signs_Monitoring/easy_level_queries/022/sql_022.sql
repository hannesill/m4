WITH MaxMapPerStay AS (
  SELECT
    ce.stay_id,
    MAX(ce.valuenum) AS max_map_per_stay
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 48 AND 58
    AND ce.itemid IN (
      220052,
      52
    )
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 40 AND 160
  GROUP BY
    ce.stay_id
)
SELECT
  ROUND(AVG(max_map_per_stay), 2) AS avg_of_max_map
FROM MaxMapPerStay;
