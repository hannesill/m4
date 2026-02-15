WITH female_medicine_admissions AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 59 AND 69
        AND a.admission_type LIKE '%EMER%'
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
)
SELECT
    CASE
        WHEN hospital_expire_flag = 0 THEN 'Discharged Alive'
        WHEN hospital_expire_flag = 1 THEN 'In-Hospital Mortality'
    END AS outcome_group,
    COUNT(*) AS total_admissions,
    COUNTIF(length_of_stay_days >= 7) AS admissions_los_ge_7_days,
    ROUND(SAFE_DIVIDE(
        COUNTIF(length_of_stay_days >= 7),
        COUNT(*)
    ) * 100, 2) AS proportion_los_ge_7_days_pct,
    ROUND(SAFE_DIVIDE(
        COUNTIF(length_of_stay_days < 7),
        (COUNT(*) - 1)
    ) * 100, 2) AS percentile_rank_of_7_days
FROM
    female_medicine_admissions
GROUP BY
    hospital_expire_flag
ORDER BY
    hospital_expire_flag;
