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
        p.gender = 'M'
        AND p.anchor_age BETWEEN 75 AND 85
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND a.dischtime >= a.admittime
),
discharge_categorization AS (
    SELECT
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN discharge_location LIKE 'HOME%' THEN 'Discharged Home'
            WHEN discharge_location IN ('SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL') THEN 'Discharged to Facility'
            ELSE 'Other'
        END AS discharge_group
    FROM
        patient_cohort
),
summary_statistics AS (
    SELECT
        discharge_group,
        COUNT(*) AS total_admissions,
        COUNTIF(length_of_stay_days >= 7) AS admissions_los_ge_7_days,
        ROUND(
            SAFE_DIVIDE(
                COUNTIF(length_of_stay_days >= 7),
                COUNT(*)
            ),
            4
        ) AS proportion_los_ge_7_days,
        ROUND(
            SAFE_DIVIDE(
                COUNTIF(length_of_stay_days <= 7),
                COUNT(*)
            ),
            4
        ) AS percentile_rank_of_7_day_los
    FROM
        discharge_categorization
    WHERE
        discharge_group IN ('In-Hospital Mortality', 'Discharged Home', 'Discharged to Facility')
    GROUP BY
        discharge_group
)
SELECT
    discharge_group,
    total_admissions,
    admissions_los_ge_7_days,
    proportion_los_ge_7_days,
    percentile_rank_of_7_day_los
FROM
    summary_statistics
ORDER BY
    CASE discharge_group
        WHEN 'Discharged Home' THEN 1
        WHEN 'Discharged to Facility' THEN 2
        WHEN 'In-Hospital Mortality' THEN 3
    END;
