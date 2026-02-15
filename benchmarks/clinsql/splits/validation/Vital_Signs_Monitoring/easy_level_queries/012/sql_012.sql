WITH mean_dbp_per_stay AS (
  SELECT
    AVG(ce.valuenum) AS avg_dbp_stay
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` icu ON p.subject_id = icu.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` ce ON icu.stay_id = ce.stay_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 49 AND 59
    AND (icu.first_careunit LIKE '%Stepdown%' OR icu.first_careunit LIKE '%Intermediate%')
    AND ce.itemid IN (220051, 8368)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 30 AND 150
  GROUP BY
    p.subject_id, icu.stay_id
)
SELECT
  ROUND(quantiles[OFFSET(3)] - quantiles[OFFSET(1)], 2) AS iqr_of_mean_dbp
FROM (
  SELECT
    APPROX_QUANTILES(avg_dbp_stay, 4) AS quantiles
  FROM
    mean_dbp_per_stay
  WHERE
    avg_dbp_stay IS NOT NULL
)
