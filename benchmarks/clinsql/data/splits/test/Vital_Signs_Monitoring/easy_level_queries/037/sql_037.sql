SELECT
    ROUND(AVG(ce.valuenum), 2) AS avg_mean_arterial_pressure
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON p.subject_id = icu.subject_id
JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON icu.stay_id = ce.stay_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 89 AND 99
    AND ce.itemid IN (220052, 225312, 224322, 456, 52)
    AND ce.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 24 HOUR)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 40 AND 140;
