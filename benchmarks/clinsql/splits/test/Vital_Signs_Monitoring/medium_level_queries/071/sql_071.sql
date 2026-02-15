WITH female_patients_in_age_range AS (
    SELECT
        p.subject_id,
        ie.stay_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 38 AND 48
        AND ie.outtime IS NOT NULL
),
avg_spo2_per_stay AS (
    SELECT
        fp.stay_id,
        AVG(ce.valuenum) AS avg_spo2
    FROM
        female_patients_in_age_range AS fp
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON fp.stay_id = ce.stay_id
    WHERE
        ce.itemid = 220277
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 50 AND 100
    GROUP BY
        fp.stay_id
)
SELECT
    'Female Patients Aged 38-48' AS cohort_description,
    COUNT(stay_id) AS total_icu_stays_in_cohort,
    ROUND(
        100 * SAFE_DIVIDE(
            SUM(CASE WHEN avg_spo2 <= 92 THEN 1 ELSE 0 END),
            COUNT(stay_id)
        ), 2
    ) AS percentile_rank_of_92_spo2,
    ROUND(AVG(avg_spo2), 2) AS cohort_mean_avg_spo2,
    ROUND(STDDEV(avg_spo2), 2) AS cohort_stddev_avg_spo2,
    APPROX_QUANTILES(avg_spo2, 100)[OFFSET(25)] AS p25_avg_spo2,
    APPROX_QUANTILES(avg_spo2, 100)[OFFSET(50)] AS p50_avg_spo2,
    APPROX_QUANTILES(avg_spo2, 100)[OFFSET(75)] AS p75_avg_spo2,
    APPROX_QUANTILES(avg_spo2, 100)[OFFSET(90)] AS p90_avg_spo2
FROM
    avg_spo2_per_stay
WHERE
    avg_spo2 IS NOT NULL;
