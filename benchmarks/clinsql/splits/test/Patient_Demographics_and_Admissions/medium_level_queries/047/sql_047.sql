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
        AND p.anchor_age BETWEEN 52 AND 62
        AND a.admission_location = 'TRANSFER FROM HOSPITAL'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND a.dischtime > a.admittime
),
discharge_stratification AS (
    SELECT
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
    COUNT(*) AS number_of_patients,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    ROUND(STDDEV(length_of_stay_days), 2) AS stddev_los_days,
    ROUND(
        (COUNTIF(length_of_stay_days < 5) * 100.0 / COUNT(*)),
        2
    ) AS percentile_rank_of_5_days
FROM
    discharge_stratification
WHERE
    discharge_category != 'Other'
GROUP BY
    discharge_category
ORDER BY
    discharge_category;
