WITH FirstHeartRate AS (
  SELECT
    ce.valuenum,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY ce.charttime ASC) as measurement_rank
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce ON p.subject_id = ce.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 38 AND 48
    AND ce.itemid IN (220045, 211)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 30 AND 200
)
SELECT
    ROUND(MIN(fhr.valuenum), 2) as min_admission_heart_rate
FROM FirstHeartRate fhr
WHERE fhr.measurement_rank = 1;
