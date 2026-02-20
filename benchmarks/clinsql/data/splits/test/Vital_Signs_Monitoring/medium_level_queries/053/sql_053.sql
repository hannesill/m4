WITH patient_cohort AS (
    SELECT
        p.subject_id,
        ie.stay_id,
        ie.intime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON a.hadm_id = ie.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 65 AND 75
        AND ie.intime IS NOT NULL
),
sbp_measurements_first_24h AS (
    SELECT
        pc.stay_id,
        ce.valuenum AS sbp_value
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        ON pc.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (
            220050,
            51
        )
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 40 AND 300
        AND ce.charttime >= pc.intime
        AND ce.charttime <= DATETIME_ADD(pc.intime, INTERVAL 24 HOUR)
),
categorized_sbp AS (
    SELECT
        sbp_value,
        CASE
            WHEN sbp_value < 140 THEN '< 140 mmHg'
            WHEN sbp_value >= 140 AND sbp_value < 160 THEN '140-159 mmHg'
            WHEN sbp_value >= 160 THEN '>= 160 mmHg'
            ELSE 'Unknown'
        END AS sbp_category
    FROM
        sbp_measurements_first_24h
)
SELECT
    sbp_category,
    COUNT(*) AS measurement_count,
    ROUND(AVG(sbp_value), 1) AS mean_sbp,
    ROUND(APPROX_QUANTILES(sbp_value, 100)[OFFSET(50)], 1) AS median_sbp,
    ROUND(APPROX_QUANTILES(sbp_value, 100)[OFFSET(25)], 1) AS q1_sbp,
    ROUND(APPROX_QUANTILES(sbp_value, 100)[OFFSET(75)], 1) AS q3_sbp,
    ROUND(
        (APPROX_QUANTILES(sbp_value, 100)[OFFSET(75)] - APPROX_QUANTILES(sbp_value, 100)[OFFSET(25)]), 1
    ) AS iqr_sbp
FROM
    categorized_sbp
WHERE
    sbp_category != 'Unknown'
GROUP BY
    sbp_category
ORDER BY
    CASE
        WHEN sbp_category = '< 140 mmHg' THEN 1
        WHEN sbp_category = '140-159 mmHg' THEN 2
        WHEN sbp_category = '>= 160 mmHg' THEN 3
    END;
