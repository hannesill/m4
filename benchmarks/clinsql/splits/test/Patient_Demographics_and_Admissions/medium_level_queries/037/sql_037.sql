WITH patient_cohort AS (
    SELECT
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 52 AND 62
        AND a.admission_type != 'EMERGENCY'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
)
SELECT
    CASE
        WHEN hospital_expire_flag = 0 THEN 'Discharged Alive'
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
    END AS outcome_group,
    COUNT(*) AS total_admissions,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS p50_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS p75_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS p90_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(95)] AS p95_los_days,
    ROUND(100 * (
        COUNTIF(length_of_stay_days <= 7) / COUNT(*)
    ), 2) AS percentile_rank_of_7_days
FROM
    patient_cohort
GROUP BY
    hospital_expire_flag
ORDER BY
    outcome_group;
