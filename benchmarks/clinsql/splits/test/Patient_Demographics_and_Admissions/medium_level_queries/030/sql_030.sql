WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days,
        CASE
            WHEN a.hospital_expire_flag = 0 THEN 'Discharged Alive'
            WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
        END AS outcome
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 44 AND 54
        AND a.admission_type = 'ELECTIVE'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) > 0
)
SELECT
    outcome,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(25)] AS p25_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS p75_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS p90_los_days
FROM
    patient_cohort
GROUP BY
    outcome
ORDER BY
    outcome;
