WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        a.discharge_location,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 49 AND 59
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
),
medicine_admissions AS (
    SELECT
        p.hadm_id,
        p.length_of_stay,
        CASE
            WHEN p.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN p.discharge_location = 'HOSPICE' THEN 'Discharged to Hospice'
            WHEN p.discharge_location IN ('HOME', 'HOME HEALTH CARE') THEN 'Discharged Home'
            ELSE 'Other'
        END AS discharge_category
    FROM
        patient_cohort p
    WHERE
        EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.services` s
            WHERE s.hadm_id = p.hadm_id AND s.curr_service = 'MED'
        )
)
SELECT
    discharge_category,
    COUNT(hadm_id) AS total_admissions,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay >= 7), COUNT(hadm_id)), 3) AS proportion_los_ge_7_days,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay >= 14), COUNT(hadm_id)), 3) AS proportion_los_ge_14_days,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay <= 7), COUNT(hadm_id)), 3) AS percentile_rank_of_7_days
FROM
    medicine_admissions
WHERE
    discharge_category IN ('Discharged Home', 'Discharged to Hospice', 'In-Hospital Mortality')
GROUP BY
    discharge_category
ORDER BY
    discharge_category;
