WITH FirstMAP AS (
  SELECT
    p.subject_id,
    ce.valuenum,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY ce.charttime ASC) as measurement_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` ce ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 52 AND 62
    AND ce.itemid IN (220052, 456)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 40 AND 140
),
MAPQuantiles AS (
  SELECT
    APPROX_QUANTILES(valuenum, 100) AS percentiles
  FROM
    FirstMAP
  WHERE
    measurement_rank = 1
)
SELECT
  ROUND(
    percentiles[OFFSET(75)] - percentiles[OFFSET(25)],
    2
  ) AS iqr_mean_arterial_pressure
FROM
  MAPQuantiles;
