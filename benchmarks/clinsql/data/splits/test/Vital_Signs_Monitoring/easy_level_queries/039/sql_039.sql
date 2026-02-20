WITH FirstRespiratoryRate AS (
    SELECT
        subject_id,
        stay_id,
        valuenum,
        ROW_NUMBER() OVER(PARTITION BY stay_id ORDER BY charttime ASC) as rn
    FROM
        `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
        itemid IN (220210, 615)
        AND valuenum IS NOT NULL
        AND valuenum BETWEEN 5 AND 50
)
SELECT
    ROUND(APPROX_QUANTILES(frr.valuenum, 100)[OFFSET(25)], 2) AS p25_respiratory_rate
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    FirstRespiratoryRate frr ON p.subject_id = frr.subject_id
WHERE
    frr.rn = 1
    AND p.gender = 'F'
    AND p.anchor_age BETWEEN 51 AND 61;
