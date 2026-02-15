WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE
            WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN a.discharge_location LIKE 'HOME%' THEN 'Discharged Home'
            WHEN a.discharge_location IN (
                'SKILLED NURSING FACILITY',
                'REHAB/DISTINCT PART HOSP',
                'LONG TERM CARE HOSPITAL'
            ) THEN 'Discharged to Facility'
            ELSE 'Other'
        END AS discharge_group
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 43 AND 53
        AND a.admission_location = 'EMERGENCY ROOM'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
)
SELECT
    discharge_group,
    COUNT(hadm_id) AS number_of_admissions,
    APPROX_QUANTILES(length_of_stay, 100)[OFFSET(50)] AS median_los_days,
    (APPROX_QUANTILES(length_of_stay, 100)[OFFSET(75)] - APPROX_QUANTILES(length_of_stay, 100)[OFFSET(25)]) AS iqr_los_days,
    ROUND(100 * (COUNTIF(length_of_stay <= 14) / COUNT(hadm_id)), 1) AS percentile_rank_of_14_day_los
FROM
    patient_cohort
WHERE
    discharge_group IN ('Discharged Home', 'Discharged to Facility', 'In-Hospital Mortality')
GROUP BY
    discharge_group
ORDER BY
    median_los_days;
