WITH MaxRRPerStay AS (
  SELECT
    MAX(ce.valuenum) AS max_rr_per_stay
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 35 AND 45
    AND ce.itemid IN (220210, 615)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 5 AND 50
  GROUP BY
    ce.stay_id
)
SELECT
  ROUND(MIN(max_rr_per_stay), 2) AS min_of_max_respiratory_rate
FROM MaxRRPerStay;
