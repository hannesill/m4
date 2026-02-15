WITH patient_cohort AS (
    SELECT
        p.subject_id,
        ie.stay_id,
        ie.intime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 54 AND 64
        AND ie.intime IS NOT NULL
),

rr_measurements_first_48h AS (
    SELECT
        pc.stay_id,
        ce.valuenum
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON pc.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (220210, 615)
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum > 0 AND ce.valuenum < 100
        AND DATETIME_DIFF(ce.charttime, pc.intime, HOUR) BETWEEN 0 AND 48
),

avg_rr_per_stay AS (
    SELECT
        stay_id,
        AVG(valuenum) AS avg_rr,
        CASE
            WHEN AVG(valuenum) < 12 THEN '< 12 (Bradypnea)'
            WHEN AVG(valuenum) >= 12 AND AVG(valuenum) <= 20 THEN '12-20 (Normal)'
            WHEN AVG(valuenum) > 20 AND AVG(valuenum) < 30 THEN '21-29 (Tachypnea)'
            WHEN AVG(valuenum) >= 30 THEN '>= 30 (Severe Tachypnea)'
            ELSE 'Unknown'
        END AS rr_category
    FROM
        rr_measurements_first_48h
    GROUP BY
        stay_id
)

SELECT
    rr_category,
    COUNT(stay_id) AS number_of_icu_stays,
    ROUND(AVG(avg_rr), 1) AS mean_of_average_rr,
    ROUND(APPROX_QUANTILES(avg_rr, 100)[OFFSET(50)], 1) AS median_of_average_rr,
    ROUND(
        (APPROX_QUANTILES(avg_rr, 100)[OFFSET(75)] - APPROX_QUANTILES(avg_rr, 100)[OFFSET(25)]), 1
    ) AS iqr_of_average_rr
FROM
    avg_rr_per_stay
WHERE
    rr_category != 'Unknown'
GROUP BY
    rr_category
ORDER BY
    CASE
        WHEN rr_category = '< 12 (Bradypnea)' THEN 1
        WHEN rr_category = '12-20 (Normal)' THEN 2
        WHEN rr_category = '21-29 (Tachypnea)' THEN 3
        WHEN rr_category = '>= 30 (Severe Tachypnea)' THEN 4
    END;
