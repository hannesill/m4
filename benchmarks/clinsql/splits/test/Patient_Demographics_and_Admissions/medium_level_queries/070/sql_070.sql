WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        a.discharge_location,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 57 AND 67
        AND a.admission_location = 'EMERGENCY ROOM'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
),
cohort_with_outcome AS (
    SELECT
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN discharge_location LIKE '%HOSPICE%' THEN 'Discharged to Hospice'
            WHEN discharge_location = 'HOME' THEN 'Discharged Home'
        END AS discharge_outcome
    FROM
        patient_cohort
)
SELECT
    discharge_outcome,
    COUNT(discharge_outcome) AS num_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_p50,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS p75_los,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS p90_los,
    ROUND(100 * COUNTIF(length_of_stay_days <= 10) / COUNT(*), 2) AS percentile_rank_of_10_days
FROM
    cohort_with_outcome
WHERE
    discharge_outcome IS NOT NULL
GROUP BY
    discharge_outcome
ORDER BY
    discharge_outcome;
