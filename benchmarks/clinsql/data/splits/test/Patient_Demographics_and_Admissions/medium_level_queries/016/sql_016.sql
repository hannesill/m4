WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        CASE
            WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN UPPER(a.discharge_location) LIKE '%HOSPICE%' THEN 'Discharged to Hospice'
            WHEN UPPER(a.discharge_location) LIKE '%HOME%' THEN 'Discharged Home'
        END AS discharge_group
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 44 AND 54
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND a.admission_type IN ('EW EMER', 'URGENT', 'DIRECT EMER', 'ELECTIVE')
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
),
filtered_cohort AS (
    SELECT
        hadm_id,
        length_of_stay,
        discharge_group
    FROM
        patient_cohort
    WHERE
        discharge_group IS NOT NULL
)
SELECT
    discharge_group,
    COUNT(hadm_id) AS number_of_admissions,
    APPROX_QUANTILES(length_of_stay, 100)[OFFSET(50)] AS p50_los_days,
    APPROX_QUANTILES(length_of_stay, 100)[OFFSET(75)] AS p75_los_days,
    APPROX_QUANTILES(length_of_stay, 100)[OFFSET(90)] AS p90_los_days,
    APPROX_QUANTILES(length_of_stay, 100)[OFFSET(95)] AS p95_los_days,
    ROUND(100 * (COUNTIF(length_of_stay < 7) / COUNT(hadm_id)), 1) AS percentile_rank_of_7_days
FROM
    filtered_cohort
GROUP BY
    discharge_group
ORDER BY
    discharge_group;
