SELECT
    ROUND(
        APPROX_QUANTILES(ce.valuenum, 100)[OFFSET(75)], 2
    ) AS p75_systolic_bp
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON p.subject_id = ce.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 59 AND 69
    AND ce.itemid IN (
        220050,
        51
    )
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 70 AND 250;
