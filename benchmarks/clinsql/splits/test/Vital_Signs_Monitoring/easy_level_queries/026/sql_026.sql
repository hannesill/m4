SELECT
    ROUND(MIN(ce.valuenum), 2) as min_respiratory_rate
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_icu.icustays` icu ON p.subject_id = icu.subject_id
JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce ON icu.stay_id = ce.stay_id
WHERE p.gender = 'M'
  AND p.anchor_age BETWEEN 39 AND 49
  AND ce.itemid IN (220210, 615)
  AND DATETIME_DIFF(ce.charttime, icu.intime, HOUR) BETWEEN 0 AND 24
  AND ce.valuenum IS NOT NULL
  AND ce.valuenum BETWEEN 5 AND 50;
