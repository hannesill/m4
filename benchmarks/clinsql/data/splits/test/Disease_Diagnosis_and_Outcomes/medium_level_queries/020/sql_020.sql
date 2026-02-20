WITH base_admissions AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 86 AND 96
),
sepsis_cohort AS (
    SELECT
        hadm_id
    FROM
        base_admissions
    WHERE
        hadm_id IN (
            SELECT DISTINCT hadm_id
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
            WHERE
                icd_code IN ('99591', 'A419', 'R6520')
                OR (icd_version = 10 AND icd_code LIKE 'A41%')
        )
        AND hadm_id NOT IN (
            SELECT DISTINCT hadm_id
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
            WHERE
                icd_code IN ('78552', 'R6521')
        )
),
categorized_admissions AS (
    SELECT
        b.hadm_id,
        b.hospital_expire_flag,
        DATETIME_DIFF(b.dischtime, b.admittime, DAY) AS length_of_stay,
        CASE
            WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) <= 3 THEN '≤3 days'
            WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) BETWEEN 4 AND 6 THEN '4-6 days'
            WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) BETWEEN 7 AND 10 THEN '7-10 days'
            ELSE '>10 days'
        END AS los_category,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
                WHERE icu.hadm_id = b.hadm_id
                  AND icu.intime < DATETIME_ADD(b.admittime, INTERVAL 1 DAY)
            ) THEN 'ICU_Day1'
            ELSE 'Non_ICU_Day1'
        END AS day1_icu_status
    FROM
        base_admissions AS b
    JOIN
        sepsis_cohort AS s ON b.hadm_id = s.hadm_id
)
SELECT
    los_category,
    day1_icu_status,
    COUNT(*) AS total_patients,
    SUM(hospital_expire_flag) AS total_deaths,
    ROUND(SAFE_DIVIDE(SUM(hospital_expire_flag) * 100.0, COUNT(*)), 2) AS mortality_rate_percent,
    APPROX_QUANTILES(
        CASE
            WHEN hospital_expire_flag = 1 THEN length_of_stay
            ELSE NULL
        END, 2
    )[OFFSET(1)] AS median_days_to_death_for_nonsurvivors
FROM
    categorized_admissions
GROUP BY
    los_category,
    day1_icu_status
ORDER BY
    CASE
        WHEN los_category = '≤3 days' THEN 1
        WHEN los_category = '4-6 days' THEN 2
        WHEN los_category = '7-10 days' THEN 3
        ELSE 4
    END,
    day1_icu_status;
