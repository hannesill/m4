WITH base_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        p.dod,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay,
        DATETIME_DIFF(p.dod, a.admittime, DAY) AS time_to_death_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
),
sepsis_admissions AS (
    SELECT
        hadm_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
    HAVING
        COUNTIF(
            (icd_version = 9 AND icd_code = '99591') OR
            (icd_version = 10 AND (icd_code LIKE 'A41%' OR icd_code = 'R6520'))
        ) > 0
        AND COUNTIF(
            (icd_version = 9 AND icd_code = '78552') OR
            (icd_version = 10 AND icd_code = 'R6521')
        ) = 0
),
final_cohort AS (
    SELECT
        bc.hadm_id,
        bc.hospital_expire_flag,
        bc.time_to_death_days,
        CASE
            WHEN bc.length_of_stay < 8 THEN '<8 days'
            ELSE '>=8 days'
        END AS los_group
    FROM
        base_cohort AS bc
    INNER JOIN
        sepsis_admissions AS sa ON bc.hadm_id = sa.hadm_id
)
SELECT
    los_group,
    COUNT(*) AS total_admissions,
    SUM(hospital_expire_flag) AS total_deaths,
    ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_percent,
    ROUND(
        GREATEST(0,
            (
                AVG(hospital_expire_flag) - 1.96 * SQRT(SAFE_DIVIDE(AVG(hospital_expire_flag) * (1 - AVG(hospital_expire_flag)), COUNT(*)))
            ) * 100
        ), 2
    ) AS mortality_ci_95_lower,
    ROUND(
        LEAST(100,
            (
                AVG(hospital_expire_flag) + 1.96 * SQRT(SAFE_DIVIDE(AVG(hospital_expire_flag) * (1 - AVG(hospital_expire_flag)), COUNT(*)))
            ) * 100
        ), 2
    ) AS mortality_ci_95_upper,
    APPROX_QUANTILES(
        IF(hospital_expire_flag = 1, time_to_death_days, NULL), 100 IGNORE NULLS
    )[OFFSET(50)] AS median_days_to_death_among_nonsurvivors
FROM
    final_cohort
GROUP BY
    los_group
ORDER BY
    los_group;
