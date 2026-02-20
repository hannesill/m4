SELECT
    ROUND(STDDEV(ce.valuenum), 2) AS stddev_sbp
FROM `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN `physionet-data.mimiciv_3_1_icu.icustays` icu ON p.subject_id = icu.subject_id
JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce ON icu.stay_id = ce.stay_id
WHERE p.gender = 'M'
  AND p.anchor_age BETWEEN 76 AND 86
  AND icu.first_careunit IN ('Medical/Surgical Intermediate Care', 'Neuro Stepdown')
  AND ce.itemid IN (220050, 51)
  AND ce.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 24 HOUR)
  AND ce.valuenum IS NOT NULL
  AND ce.valuenum BETWEEN 70 AND 250;
