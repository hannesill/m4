WITH patient_cohort AS (
    SELECT
        ie.stay_id
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON a.hadm_id = ie.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 85 AND 95
        AND ie.stay_id IS NOT NULL
),
temperature_measurements AS (
    SELECT
        pc.stay_id,
        CASE
            WHEN ce.itemid = 223761 THEN (ce.valuenum - 32) * 5 / 9
            WHEN ce.itemid = 678 THEN (ce.valuenum - 32) * 5 / 9
            ELSE ce.valuenum
        END AS temp_celsius
    FROM patient_cohort AS pc
    INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        ON pc.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (223762, 223761, 676, 678)
        AND ce.valuenum IS NOT NULL
),
avg_stay_temperatures AS (
    SELECT
        stay_id,
        AVG(tm.temp_celsius) AS avg_temp_c
    FROM temperature_measurements AS tm
    WHERE
        tm.temp_celsius BETWEEN 32 AND 43
    GROUP BY
        stay_id
)
SELECT
    36.0 AS target_temp_c,
    COUNT(stay_id) AS total_icu_stays,
    COUNTIF(avg_temp_c < 36.0) AS stays_with_lower_avg_temp,
    ROUND(100.0 * COUNTIF(avg_temp_c < 36.0) / COUNT(stay_id), 2) AS percentile_rank_of_target_temp,
    ROUND(AVG(avg_temp_c), 2) AS cohort_mean_avg_temp,
    ROUND(STDDEV(avg_temp_c), 2) AS cohort_stddev_avg_temp,
    ROUND(MIN(avg_temp_c), 2) AS cohort_min_avg_temp,
    ROUND(MAX(avg_temp_c), 2) AS cohort_max_avg_temp,
    ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(10)], 2) AS p10_avg_temp,
    ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(25)], 2) AS p25_avg_temp,
    ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(50)], 2) AS p50_median_avg_temp,
    ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(75)], 2) AS p75_avg_temp,
    ROUND(APPROX_QUANTILES(avg_temp_c, 100)[OFFSET(90)], 2) AS p90_avg_temp
FROM
    avg_stay_temperatures
WHERE
    avg_temp_c IS NOT NULL;
