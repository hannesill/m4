WITH initial_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
            ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
),
sepsis_cohort AS (
    SELECT
        c.hadm_id,
        c.hospital_expire_flag,
        c.los_days
    FROM
        initial_cohort AS c
    WHERE
        EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
            WHERE hadm_id = c.hadm_id
            AND (
                icd_code = '99591'
                OR icd_code LIKE 'A41%'
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
            WHERE hadm_id = c.hadm_id
            AND (
                icd_code = '78552'
                OR icd_code = 'R6521'
            )
        )
),
strata_scaffold AS (
    SELECT '<=7 days' AS los_stratum
    UNION ALL
    SELECT '>7 days' AS los_stratum
),
stratified_metrics AS (
    SELECT
        CASE
            WHEN los_days <= 7 THEN '<=7 days'
            ELSE '>7 days'
        END AS los_stratum,
        COUNT(DISTINCT hadm_id) AS N,
        AVG(hospital_expire_flag) AS avg_mortality,
        CAST(APPROX_QUANTILES(
            CASE WHEN hospital_expire_flag = 1 THEN los_days END, 2
        )[OFFSET(1)] AS INT64) AS median_time_to_death_days
    FROM
        sepsis_cohort
    GROUP BY
        los_stratum
),
scaffolded_metrics AS (
    SELECT
        s.los_stratum,
        COALESCE(m.N, 0) AS N,
        COALESCE(m.avg_mortality, 0) AS avg_mortality,
        m.median_time_to_death_days
    FROM
        strata_scaffold AS s
    LEFT JOIN
        stratified_metrics AS m ON s.los_stratum = m.los_stratum
),
comparison_metrics AS (
    SELECT
        los_stratum,
        N,
        avg_mortality,
        median_time_to_death_days,
        MAX(CASE WHEN los_stratum = '>7 days' THEN avg_mortality END) OVER() AS mortality_avg_gt7,
        MAX(CASE WHEN los_stratum = '<=7 days' THEN avg_mortality END) OVER() AS mortality_avg_le7
    FROM
        scaffolded_metrics
)
SELECT
    c.los_stratum,
    c.N,
    ROUND(c.avg_mortality * 100, 2) AS mortality_rate_percent,
    c.median_time_to_death_days,
    ROUND((COALESCE(c.mortality_avg_gt7, 0) - COALESCE(c.mortality_avg_le7, 0)) * 100, 2) AS absolute_mortality_difference_percent,
    ROUND(SAFE_DIVIDE(
        (COALESCE(c.mortality_avg_gt7, 0) - COALESCE(c.mortality_avg_le7, 0)),
        COALESCE(c.mortality_avg_le7, 0)
    ) * 100, 2) AS relative_mortality_difference_percent
FROM
    comparison_metrics AS c
ORDER BY
    CASE
        WHEN c.los_stratum = '<=7 days' THEN 1
        WHEN c.los_stratum = '>7 days' THEN 2
    END;
