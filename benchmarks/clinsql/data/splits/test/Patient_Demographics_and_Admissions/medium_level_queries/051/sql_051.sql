WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 68 AND 78
        AND a.admission_location = 'EMERGENCY ROOM'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
)
SELECT
    CASE
        WHEN hospital_expire_flag = 0 THEN 'Discharged Alive'
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
    END AS survival_status,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    ROUND(STDDEV_SAMP(length_of_stay_days), 2) AS stddev_los_days,
    ROUND(
        100 * (
            COUNTIF(length_of_stay_days <= 7) / COUNT(hadm_id)
        ), 1
    ) AS percentile_rank_of_7_days
FROM
    patient_cohort
GROUP BY
    survival_status
ORDER BY
    survival_status;
