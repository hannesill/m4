WITH FirstSpO2Measurements AS (
  SELECT
    ce.valuenum,
    ROW_NUMBER() OVER(PARTITION BY ce.subject_id, ce.stay_id ORDER BY ce.charttime ASC) as measurement_rank
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
    ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 77 AND 87
    AND ce.itemid IN (220277, 646)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 80 AND 100
)
SELECT
    ROUND(STDDEV(valuenum), 2) as stddev_first_spo2
FROM FirstSpO2Measurements
WHERE
  measurement_rank = 1;
