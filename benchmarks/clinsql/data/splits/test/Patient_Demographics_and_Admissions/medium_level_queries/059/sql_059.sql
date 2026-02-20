WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days,
        CASE
            WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN a.discharge_location = 'HOME' THEN 'Discharged Home'
            WHEN a.discharge_location = 'HOSPICE' THEN 'Discharged to Hospice'
            ELSE 'Other'
        END AS discharge_category
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 75 AND 85
        AND a.admission_location = 'TRANSFER FROM HOSPITAL'
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
)
SELECT
    discharge_category,
    COUNT(*) AS total_admissions,
    COUNTIF(length_of_stay_days >= 7) AS admissions_los_ge_7,
    ROUND(
        SAFE_DIVIDE(
            COUNTIF(length_of_stay_days >= 7),
            COUNT(*)
        ) * 100,
    2) AS proportion_los_ge_7_pct,
    ROUND(
        SAFE_DIVIDE(
            COUNTIF(length_of_stay_days <= 7),
            COUNT(*)
        ) * 100,
    2) AS percentile_rank_of_7_days
FROM
    patient_cohort
WHERE
    discharge_category IN ('Discharged Home', 'Discharged to Hospice', 'In-Hospital Mortality')
GROUP BY
    discharge_category
ORDER BY
    discharge_category;
