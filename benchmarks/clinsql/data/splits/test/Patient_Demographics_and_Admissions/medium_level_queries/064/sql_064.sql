WITH patient_cohort AS (
    SELECT DISTINCT
        a.hadm_id,
        a.discharge_location,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu
        ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 63 AND 73
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
),
discharge_outcomes AS (
    SELECT
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN UPPER(discharge_location) LIKE '%HOSPICE%' THEN 'Discharged to Hospice'
            WHEN UPPER(discharge_location) LIKE '%HOME%' THEN 'Discharged Home'
            ELSE 'Other'
        END AS discharge_category
    FROM
        patient_cohort
)
SELECT
    discharge_category,
    COUNT(*) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days,
    ROUND(
        SAFE_DIVIDE(
            COUNTIF(length_of_stay_days <= 10) * 100.0,
            COUNT(*)
        ), 2
    ) AS percentile_rank_of_10_days
FROM
    discharge_outcomes
WHERE
    discharge_category IN ('In-Hospital Mortality', 'Discharged to Hospice', 'Discharged Home')
GROUP BY
    discharge_category
ORDER BY
    discharge_category;
