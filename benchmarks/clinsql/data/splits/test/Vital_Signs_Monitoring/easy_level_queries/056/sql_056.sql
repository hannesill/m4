SELECT
    ROUND(APPROX_QUANTILES(ce.valuenum, 2)[OFFSET(1)], 2) AS median_temperature_F
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` icu ON p.subject_id = icu.subject_id
JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` ce ON icu.stay_id = ce.stay_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 46 AND 56
    AND ce.itemid IN (223762, 676)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 95 AND 110
    AND ce.charttime >= icu.intime AND ce.charttime <= DATETIME_ADD(icu.intime, INTERVAL 24 HOUR);
