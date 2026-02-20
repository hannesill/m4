WITH ed_admissions_cohort AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 67 AND 77
        AND a.admission_location = 'EMERGENCY ROOM'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) > 0
)
SELECT
    CASE
        WHEN hospital_expire_flag = 0 THEN 'Discharged Alive'
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
    END AS outcome_group,
    COUNT(hadm_id) AS total_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS avg_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay_days >= 7), COUNT(hadm_id)), 4) AS proportion_los_ge_7_days,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay_days >= 14), COUNT(hadm_id)), 4) AS proportion_los_ge_14_days,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay_days <= 10), COUNT(hadm_id)), 4) AS percentile_rank_of_10_day_los
FROM
    ed_admissions_cohort
GROUP BY
    outcome_group
ORDER BY
    outcome_group DESC;
