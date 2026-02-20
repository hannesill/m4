WITH patient_los AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 83 AND 93
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
),
los_statistics AS (
    SELECT
        hospital_expire_flag,
        COUNT(hadm_id) AS total_admissions,
        AVG(length_of_stay_days) AS mean_los,
        APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_p50,
        APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS p75_los,
        APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS p90_los,
        SAFE_DIVIDE(COUNTIF(length_of_stay_days <= 5), COUNT(hadm_id)) * 100 AS percentile_rank_of_5_days
    FROM
        patient_los
    GROUP BY
        hospital_expire_flag
)
SELECT
    CASE
        WHEN hospital_expire_flag = 0 THEN 'Discharged Alive'
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        ELSE 'Unknown'
    END AS outcome_status,
    total_admissions,
    ROUND(mean_los, 2) AS mean_los_days,
    ROUND(median_los_p50, 2) AS median_los_days_p50,
    ROUND(p75_los, 2) AS p75_los_days,
    ROUND(p90_los, 2) AS p90_los_days,
    ROUND(percentile_rank_of_5_days, 2) AS percentile_rank_of_5_day_stay
FROM
    los_statistics
ORDER BY
    outcome_status;
