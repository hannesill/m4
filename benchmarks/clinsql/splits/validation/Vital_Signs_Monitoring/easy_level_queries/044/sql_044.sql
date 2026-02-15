WITH MaxMapPerStay AS (
    SELECT
        stay_id,
        subject_id,
        MAX(valuenum) AS max_map_during_stay
    FROM
        `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
        itemid IN (220052, 456)
        AND valuenum IS NOT NULL
        AND valuenum BETWEEN 40 AND 140
    GROUP BY
        stay_id, subject_id
)
SELECT
    ROUND(APPROX_QUANTILES(m.max_map_during_stay, 2)[OFFSET(1)], 2) AS median_of_max_map
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    MaxMapPerStay m ON p.subject_id = m.subject_id
WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 82 AND 92;
