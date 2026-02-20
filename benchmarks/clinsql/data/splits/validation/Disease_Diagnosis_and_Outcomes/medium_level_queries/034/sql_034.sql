WITH cohort AS (
    SELECT
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 70 AND 80
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code LIKE '428%' OR
                d.icd_code LIKE 'I50%'
            )
        )
),
aggregated_metrics AS (
    SELECT
        CASE
            WHEN los_days < 8 THEN '<8 days'
            ELSE '>=8 days'
        END AS los_stratum,
        COUNT(hadm_id) AS N,
        ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_percent,
        CAST(APPROX_QUANTILES(
            CASE WHEN hospital_expire_flag = 1 THEN los_days END, 2
        )[OFFSET(1)] AS INT64) AS median_time_to_death_days
    FROM
        cohort
    GROUP BY
        los_stratum
),
strata_scaffold AS (
    SELECT '<8 days' AS los_stratum
    UNION ALL
    SELECT '>=8 days' AS los_stratum
)
SELECT
    s.los_stratum,
    COALESCE(agg.N, 0) AS N,
    agg.mortality_rate_percent,
    agg.median_time_to_death_days
FROM
    strata_scaffold AS s
LEFT JOIN
    aggregated_metrics AS agg
    ON s.los_stratum = agg.los_stratum
ORDER BY
    CASE
        WHEN s.los_stratum = '<8 days' THEN 1
        WHEN s.los_stratum = '>=8 days' THEN 2
    END;
