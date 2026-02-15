WITH patient_los_and_outcome AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days,
        CASE
            WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN UPPER(a.discharge_location) LIKE '%HOSPICE%' THEN 'Discharged to Hospice'
            WHEN UPPER(a.discharge_location) LIKE '%HOME%' THEN 'Discharged Home'
            ELSE 'Other'
        END AS outcome_category
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 75 AND 85
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND a.admission_type IN ('EW EMER.', 'URGENT', 'ELECTIVE', 'DIRECT EMER.')
        AND a.dischtime >= a.admittime
)
SELECT
    outcome_category,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    ROUND(STDDEV(length_of_stay_days), 2) AS stddev_los_days
FROM
    patient_los_and_outcome
WHERE
    outcome_category IN ('Discharged Home', 'Discharged to Hospice', 'In-Hospital Mortality')
GROUP BY
    outcome_category
ORDER BY
    outcome_category;
