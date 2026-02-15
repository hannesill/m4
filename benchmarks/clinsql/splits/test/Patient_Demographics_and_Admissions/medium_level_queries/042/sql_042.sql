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
        AND p.anchor_age BETWEEN 57 AND 67
        AND a.admission_type IN ('URGENT', 'EMERGENCY', 'EW EMER', 'DIRECT EMER')
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
)
SELECT
    CASE
        WHEN hospital_expire_flag = 0 THEN 'Discharged Alive'
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
    END AS outcome,
    COUNT(hadm_id) AS total_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    APPROX_QUANTILES(length_of_stay_days, 101)[OFFSET(50)] AS median_los_p50,
    APPROX_QUANTILES(length_of_stay_days, 101)[OFFSET(75)] AS los_p75,
    APPROX_QUANTILES(length_of_stay_days, 101)[OFFSET(90)] AS los_p90,
    ROUND(
        100 * SAFE_DIVIDE(
            COUNTIF(length_of_stay_days <= 5),
            COUNT(hadm_id)
        ), 2
    ) AS percentile_rank_of_5_day_stay
FROM
    patient_cohort
WHERE length_of_stay_days >= 0
GROUP BY
    hospital_expire_flag
ORDER BY
    outcome;
