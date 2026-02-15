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
        AND p.anchor_age BETWEEN 63 AND 73
        AND a.admission_location = 'TRANSFER FROM HOSPITAL'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND a.dischtime > a.admittime
), discharge_categorization AS (
    SELECT
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN discharge_location = 'HOME' THEN 'Discharged Home'
            WHEN discharge_location LIKE 'HOSPICE%' THEN 'Discharged to Hospice'
            ELSE 'Other'
        END AS discharge_outcome
    FROM
        patient_cohort
)
SELECT
    discharge_outcome,
    COUNT(discharge_outcome) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    ROUND(STDDEV(length_of_stay_days), 2) AS stddev_los_days
FROM
    discharge_categorization
WHERE
    discharge_outcome IN ('In-Hospital Mortality', 'Discharged Home', 'Discharged to Hospice')
GROUP BY
    discharge_outcome
ORDER BY
    mean_los_days DESC;
