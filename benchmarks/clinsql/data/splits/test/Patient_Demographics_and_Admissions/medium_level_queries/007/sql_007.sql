WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 78 AND 88
        AND a.admission_location = 'TRANSFER FROM HOSPITAL'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
),
los_statistics AS (
    SELECT
        hospital_expire_flag,
        COUNT(hadm_id) AS number_of_admissions,
        APPROX_QUANTILES(length_of_stay_days, 100) AS los_percentiles,
        ROUND(
            100 * SAFE_DIVIDE(
                COUNTIF(length_of_stay_days <= 10),
                COUNT(length_of_stay_days)
            ), 2
        ) AS percentile_rank_of_10_day_los
    FROM
        patient_cohort
    GROUP BY
        hospital_expire_flag
)
SELECT
    CASE
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        ELSE 'Discharged Alive'
    END AS outcome,
    number_of_admissions,
    los_percentiles[OFFSET(50)] AS p50_los_days,
    los_percentiles[OFFSET(75)] AS p75_los_days,
    los_percentiles[OFFSET(90)] AS p90_los_days,
    los_percentiles[OFFSET(95)] AS p95_los_days,
    percentile_rank_of_10_day_los
FROM
    los_statistics
ORDER BY
    outcome DESC;
