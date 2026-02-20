WITH FirstMAP AS (
  SELECT
    ce.subject_id,
    ce.stay_id,
    ce.valuenum,
    ROW_NUMBER() OVER(PARTITION BY ce.subject_id, ce.stay_id ORDER BY ce.charttime ASC) as rn
  FROM
    `physionet-data.mimiciv_3_1_icu.chartevents` ce
  WHERE
    ce.itemid IN (220052, 225312, 220181, 456)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 40 AND 140
)
SELECT
  ROUND(STDDEV(fm.valuenum), 2) AS stddev_first_map
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
  FirstMAP fm ON p.subject_id = fm.subject_id
WHERE
  p.gender = 'M'
  AND p.anchor_age BETWEEN 55 AND 65
  AND fm.rn = 1;
