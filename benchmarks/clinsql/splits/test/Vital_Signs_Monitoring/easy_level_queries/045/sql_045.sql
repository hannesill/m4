WITH FirstRespiratoryRate AS (
    SELECT
        ce.valuenum,
        ROW_NUMBER() OVER(PARTITION BY ce.subject_id, ce.stay_id ORDER BY ce.charttime ASC) as rn
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce
        ON p.subject_id = ce.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 51 AND 61
        AND ce.itemid IN (220210, 615)
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 5 AND 50
)
SELECT
    ROUND(STDDEV(frr.valuenum), 2) as stddev_first_respiratory_rate
FROM FirstRespiratoryRate frr
WHERE frr.rn = 1;
