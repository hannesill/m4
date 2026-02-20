WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        a.discharge_location,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 41 AND 51
        AND a.admission_location = 'EMERGENCY ROOM'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
),

categorized_admissions AS (
    SELECT
        hadm_id,
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN discharge_location = 'HOME' THEN 'Discharged Home'
            WHEN discharge_location IN (
                'SKILLED NURSING FACILITY',
                'REHAB/DISTINCT PART HOSP',
                'LONG TERM CARE HOSPITAL'
            ) THEN 'Discharged to Facility'
            ELSE 'Other'
        END AS discharge_category
    FROM
        patient_cohort
)

SELECT
    discharge_category,
    COUNT(hadm_id) AS total_admissions,
    COUNTIF(length_of_stay_days >= 7) AS admissions_los_ge_7_days,
    ROUND(
        COUNTIF(length_of_stay_days >= 7) * 100.0 / COUNT(hadm_id),
        2
    ) AS proportion_los_ge_7_days_pct,
    ROUND(
        COUNTIF(length_of_stay_days < 10) * 100.0 / COUNT(hadm_id),
        2
    ) AS percentile_rank_of_10_day_los
FROM
    categorized_admissions
WHERE
    discharge_category IN ('In-Hospital Mortality', 'Discharged Home', 'Discharged to Facility')
GROUP BY
    discharge_category
ORDER BY
    discharge_category;
