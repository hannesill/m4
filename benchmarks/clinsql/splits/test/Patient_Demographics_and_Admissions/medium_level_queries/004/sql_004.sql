WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        a.discharge_location,
        a.hospital_expire_flag,
        GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 89 AND 99
        AND a.admission_type NOT LIKE '%EMER%'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
),
cohort_with_disposition AS (
    SELECT
        hadm_id,
        length_of_stay_days,
        CASE
            WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN UPPER(discharge_location) LIKE '%HOSPICE%' THEN 'Discharged to Hospice'
            WHEN UPPER(discharge_location) LIKE '%HOME%' THEN 'Discharged Home'
            ELSE 'Other'
        END AS disposition_category
    FROM
        patient_cohort
),
final_cohort AS (
    SELECT
        hadm_id,
        length_of_stay_days,
        disposition_category
    FROM
        cohort_with_disposition
    WHERE
        disposition_category IN ('In-Hospital Mortality', 'Discharged to Hospice', 'Discharged Home')
)
SELECT
    disposition_category,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days_p50,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS los_p75,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS los_p90,
    ROUND(
        100 * SAFE_DIVIDE(
            COUNTIF(length_of_stay_days < 5),
            COUNT(hadm_id)
        ), 2
    ) AS percentile_rank_of_5_days
FROM
    final_cohort
GROUP BY
    disposition_category
ORDER BY
    disposition_category;
