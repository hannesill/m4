WITH patient_admissions AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        a.discharge_location,
        DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 64 AND 74
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND a.dischtime >= a.admittime
),
discharge_categorization AS (
    SELECT
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN discharge_location IN ('HOME', 'HOME HEALTH CARE') THEN 'Discharged Home'
            WHEN discharge_location IN ('SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL') THEN 'Discharged to Facility'
            ELSE 'Other'
        END AS discharge_group
    FROM
        patient_admissions
)
SELECT
    discharge_group,
    COUNT(*) AS total_admissions,
    COUNTIF(length_of_stay_days >= 7) AS long_los_admissions_ge7_days,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay_days >= 7), COUNT(*)), 4) AS proportion_long_los,
    ROUND(SAFE_DIVIDE(COUNTIF(length_of_stay_days < 14), COUNT(*)), 4) AS percentile_rank_of_14_day_los
FROM
    discharge_categorization
WHERE
    discharge_group != 'Other'
GROUP BY
    discharge_group
ORDER BY
    discharge_group;
