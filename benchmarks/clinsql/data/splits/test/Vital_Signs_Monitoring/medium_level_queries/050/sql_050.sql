WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
),
cohort_icu_stays AS (
    SELECT
        pc.subject_id,
        pc.hadm_id,
        ie.stay_id,
        ie.intime
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON pc.hadm_id = ie.hadm_id
    WHERE
        pc.age_at_admission BETWEEN 67 AND 77
        AND ie.intime IS NOT NULL
),
hr_measurements_first_24h AS (
    SELECT
        cis.stay_id,
        ce.valuenum
    FROM
        cohort_icu_stays AS cis
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        ON cis.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (220045, 211)
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 30 AND 250
        AND ce.charttime >= cis.intime
        AND ce.charttime <= DATETIME_ADD(cis.intime, INTERVAL 24 HOUR)
),
avg_hr_per_stay AS (
    SELECT
        stay_id,
        AVG(valuenum) AS avg_hr
    FROM
        hr_measurements_first_24h
    GROUP BY
        stay_id
)
SELECT
    ROUND(
        (COUNTIF(avg_hr <= 110) * 100.0 / COUNT(*)), 2
    ) AS percentile_rank_of_110_bpm,
    COUNT(*) AS total_icu_stays_in_cohort,
    ROUND(AVG(avg_hr), 2) AS population_mean_avg_hr,
    ROUND(STDDEV(avg_hr), 2) AS population_stddev_avg_hr,
    ROUND(APPROX_QUANTILES(avg_hr, 100)[OFFSET(25)], 2) AS p25_avg_hr,
    ROUND(APPROX_QUANTILES(avg_hr, 100)[OFFSET(50)], 2) AS p50_avg_hr_median,
    ROUND(APPROX_QUANTILES(avg_hr, 100)[OFFSET(75)], 2) AS p75_avg_hr,
    ROUND(APPROX_QUANTILES(avg_hr, 100)[OFFSET(90)], 2) AS p90_avg_hr,
    ROUND(MIN(avg_hr), 2) AS min_avg_hr_in_cohort,
    ROUND(MAX(avg_hr), 2) AS max_avg_hr_in_cohort
FROM
    avg_hr_per_stay;
