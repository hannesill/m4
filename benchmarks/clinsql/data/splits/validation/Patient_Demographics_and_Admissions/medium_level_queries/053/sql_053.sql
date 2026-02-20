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
        p.gender = 'F'
        AND p.anchor_age BETWEEN 77 AND 87
        AND a.admission_type = 'EW EMER.'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
),
discharge_categorization AS (
    SELECT
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN UPPER(discharge_location) LIKE '%HOSPICE%' THEN 'Discharged to Hospice'
            WHEN UPPER(discharge_location) LIKE '%HOME%' THEN 'Discharged Home'
            ELSE 'Other'
        END AS discharge_outcome
    FROM
        patient_cohort
)
SELECT
    discharge_outcome,
    COUNT(*) AS number_of_admissions,
    ROUND(APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)], 1) AS median_los_days,
    ROUND(APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(25)], 1) AS q1_los_days,
    ROUND(APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)], 1) AS q3_los_days,
    ROUND(
        APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] -
        APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(25)],
    1) AS iqr_los_days
FROM
    discharge_categorization
WHERE
    discharge_outcome IN ('In-Hospital Mortality', 'Discharged to Hospice', 'Discharged Home')
GROUP BY
    discharge_outcome
ORDER BY
    discharge_outcome;
