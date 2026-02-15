WITH FirstSpO2 AS (
    SELECT
        ce.valuenum,
        ROW_NUMBER() OVER(PARTITION BY ce.subject_id, ce.stay_id ORDER BY ce.charttime ASC) as rn
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
        ON p.subject_id = ce.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 37 AND 47
        AND ce.itemid IN (220277, 646)
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 80 AND 100
)
SELECT
    ROUND(
        (APPROX_QUANTILES(valuenum, 4)[OFFSET(3)] - APPROX_QUANTILES(valuenum, 4)[OFFSET(1)]),
        2
    ) AS iqr_spo2
FROM FirstSpO2
WHERE rn = 1;
