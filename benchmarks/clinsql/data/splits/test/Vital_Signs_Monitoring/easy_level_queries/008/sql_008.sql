SELECT
    ROUND(MAX(ce.valuenum), 2) AS max_respiratory_rate
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON p.subject_id = icu.subject_id
JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON icu.stay_id = ce.stay_id
WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 52 AND 62
    AND ce.itemid IN (220210, 615)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 5 AND 50
    AND TIMESTAMP_DIFF(ce.charttime, icu.intime, DAY) >= 1;
