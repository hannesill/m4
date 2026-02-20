WITH FirstGCSTotal AS (
  SELECT
    ce.valuenum,
    ROW_NUMBER() OVER(PARTITION BY ce.stay_id ORDER BY ce.charttime ASC) as rn
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 77 AND 87
    AND ce.itemid IN (226758, 198)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 3 AND 15
)
SELECT
  ROUND(AVG(valuenum), 2) AS avg_first_gcs_total
FROM
  FirstGCSTotal
WHERE
  rn = 1;
