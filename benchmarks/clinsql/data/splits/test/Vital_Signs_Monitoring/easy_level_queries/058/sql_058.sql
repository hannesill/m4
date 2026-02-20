WITH min_temp_per_stay AS (
  SELECT
    MIN(ce.valuenum) AS min_temperature
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 74 AND 84
    AND ce.itemid IN (223762, 676)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 95 AND 110
  GROUP BY
    p.subject_id, ce.stay_id
)
SELECT
    ROUND(
        APPROX_QUANTILES(min_temperature, 2)[OFFSET(1)],
        2
    ) AS median_of_min_temperature
FROM min_temp_per_stay;
