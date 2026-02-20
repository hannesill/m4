WITH strata_combinations AS (
    SELECT severity_group, los_group
    FROM
        (SELECT CAST('Higher-Severity (ICU)' AS STRING) AS severity_group UNION ALL SELECT 'Lower-Severity (Non-ICU)') AS severities,
        (SELECT CAST('<8 days' AS STRING) AS los_group UNION ALL SELECT '>=8 days') AS los_bins
),
cohort AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
                WHERE icu.hadm_id = a.hadm_id
            ) THEN 'Higher-Severity (ICU)'
            ELSE 'Lower-Severity (Non-ICU)'
        END AS severity_group,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) < 8 THEN '<8 days'
            ELSE '>=8 days'
        END AS los_group,
        CAST(EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = a.hadm_id
            AND (
                (d.icd_version = 9 AND d.icd_code LIKE '585%') OR
                (d.icd_version = 10 AND d.icd_code LIKE 'N18%')
            )
        ) AS INT64) AS has_ckd,
        CAST(EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = a.hadm_id
            AND (
                (d.icd_version = 9 AND d.icd_code LIKE '250%') OR
                (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E12', 'E13'))
            )
        ) AS INT64) AS has_diabetes
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 80 AND 90
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = a.hadm_id
            AND (
                (d.icd_version = 9 AND d.icd_code LIKE '428%') OR
                (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
            )
        )
        AND a.dischtime IS NOT NULL
)
SELECT
    s.severity_group,
    s.los_group,
    COUNT(c.hadm_id) AS patient_count,
    ROUND(COALESCE(AVG(c.hospital_expire_flag) * 100, 0), 2) AS mortality_rate_pct,
    ROUND(COALESCE(AVG(c.has_ckd) * 100, 0), 2) AS ckd_prevalence_pct,
    ROUND(COALESCE(AVG(c.has_diabetes) * 100, 0), 2) AS diabetes_prevalence_pct
FROM strata_combinations AS s
LEFT JOIN cohort AS c
    ON s.severity_group = c.severity_group AND s.los_group = c.los_group
GROUP BY
    s.severity_group,
    s.los_group
ORDER BY
    s.severity_group DESC,
    s.los_group;
