WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days,
        CASE
            WHEN a.hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
            WHEN a.discharge_location IN ('HOME', 'HOME HEALTH CARE') THEN 'Discharged Home'
            WHEN a.discharge_location IN ('SKILLED NURSING FACILITY', 'REHAB/DISTINCT PART HOSP', 'LONG TERM CARE HOSPITAL') THEN 'Discharged to Facility'
            ELSE 'Other'
        END AS discharge_outcome
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 86 AND 96
        AND a.admission_type = 'URGENT'
        AND a.insurance = 'Medicare'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
)
SELECT
    discharge_outcome,
    COUNT(*) AS number_of_admissions,
    ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_p50,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(75)] AS los_p75,
    APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(90)] AS los_p90,
    ROUND(100.0 * COUNTIF(length_of_stay_days <= 10) / COUNT(*), 2) AS percentile_rank_of_10_days
FROM
    patient_cohort
WHERE
    discharge_outcome IN ('Discharged Home', 'Discharged to Facility', 'In-Hospital Mortality')
GROUP BY
    discharge_outcome
ORDER BY
    number_of_admissions DESC;
