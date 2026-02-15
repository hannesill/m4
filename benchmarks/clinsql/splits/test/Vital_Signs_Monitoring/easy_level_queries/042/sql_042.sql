WITH MaxRRPerPatient AS (
  SELECT
    p.subject_id,
    MAX(ce.valuenum) AS max_respiratory_rate
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` ce ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 63 AND 73
    AND ce.itemid IN (220210, 615)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 5 AND 50
  GROUP BY
    p.subject_id
)
SELECT
  ROUND(STDDEV(m.max_respiratory_rate), 2) AS stddev_of_max_rr
FROM
  MaxRRPerPatient m;
