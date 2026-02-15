SELECT
    ROUND(MAX(ce.valuenum), 2) as max_respiratory_rate
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_icu.icustays` icu ON p.subject_id = icu.subject_id
JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce ON icu.stay_id = ce.stay_id
WHERE p.gender = 'F'
  AND p.anchor_age BETWEEN 38 AND 48
  AND ce.itemid IN (220210, 615)
  AND ce.valuenum IS NOT NULL
  AND ce.valuenum BETWEEN 5 AND 50
  AND ce.charttime >= icu.intime
  AND ce.charttime <= DATETIME_ADD(icu.intime, INTERVAL 24 HOUR);
