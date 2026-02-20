WITH
base_admissions AS (
    SELECT
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_type,
        a.hospital_expire_flag
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 52 AND 62
),
diagnosis_flags AS (
    SELECT
        hadm_id,
        MAX(CASE
            WHEN (icd_version = 9 AND icd_code = '99591')
              OR (icd_version = 10 AND icd_code LIKE 'A41%')
            THEN 1
            ELSE 0
        END) AS has_sepsis,
        MAX(CASE
            WHEN (icd_version = 9 AND icd_code = '78552')
              OR (icd_version = 10 AND icd_code = 'R6521')
            THEN 1
            ELSE 0
        END) AS has_septic_shock
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
),
comorbidity_counts AS (
    SELECT
        hadm_id,
        COUNT(DISTINCT icd_code) AS comorbidity_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
),
sepsis_cohort AS (
    SELECT
        b.hadm_id,
        b.hospital_expire_flag,
        c.comorbidity_count,
        CASE
            WHEN d.has_septic_shock = 1 THEN 'Septic Shock'
            ELSE 'Sepsis without Septic Shock'
        END AS sepsis_severity,
        CASE
            WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 days'
            WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 days'
            WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) >= 8 THEN '>=8 days'
            ELSE NULL
        END AS los_bucket,
        CASE
            WHEN b.admission_type = 'EMERGENCY' THEN 'Emergent'
            ELSE 'Non-Emergent'
        END AS admission_type_group
    FROM
        base_admissions AS b
    INNER JOIN
        diagnosis_flags AS d ON b.hadm_id = d.hadm_id
    INNER JOIN
        comorbidity_counts AS c ON b.hadm_id = c.hadm_id
    WHERE
        d.has_sepsis = 1
        AND b.dischtime IS NOT NULL AND b.admittime IS NOT NULL
        AND DATETIME_DIFF(b.dischtime, b.admittime, DAY) >= 1
),
strata_scaffold AS (
    SELECT
        sepsis_severity,
        los_bucket,
        los_sort_order,
        admission_type_group
    FROM
        (
            SELECT 'Sepsis without Septic Shock' AS sepsis_severity UNION ALL
            SELECT 'Septic Shock' AS sepsis_severity
        ) AS s
    CROSS JOIN
        (
            SELECT '1-3 days' AS los_bucket, 1 AS los_sort_order UNION ALL
            SELECT '4-7 days' AS los_bucket, 2 AS los_sort_order UNION ALL
            SELECT '>=8 days' AS los_bucket, 3 AS los_sort_order
        ) AS l
    CROSS JOIN
        (
            SELECT 'Emergent' AS admission_type_group UNION ALL
            SELECT 'Non-Emergent' AS admission_type_group
        ) AS a
),
aggregated_data AS (
    SELECT
        sepsis_severity,
        los_bucket,
        admission_type_group,
        COUNT(hadm_id) AS number_of_admissions,
        AVG(hospital_expire_flag) AS avg_mortality,
        AVG(comorbidity_count) AS average_comorbidity_count
    FROM
        sepsis_cohort
    WHERE
        los_bucket IS NOT NULL
    GROUP BY
        sepsis_severity,
        los_bucket,
        admission_type_group
)
SELECT
    sc.sepsis_severity,
    sc.los_bucket,
    sc.admission_type_group,
    COALESCE(agg.number_of_admissions, 0) AS number_of_admissions,
    ROUND(COALESCE(agg.avg_mortality, 0) * 100, 2) AS in_hospital_mortality_rate_pct,
    ROUND(COALESCE(agg.average_comorbidity_count, 0), 2) AS average_comorbidity_count
FROM
    strata_scaffold AS sc
LEFT JOIN
    aggregated_data AS agg
    ON sc.sepsis_severity = agg.sepsis_severity
    AND sc.los_bucket = agg.los_bucket
    AND sc.admission_type_group = agg.admission_type_group
ORDER BY
    sc.sepsis_severity DESC,
    sc.los_sort_order,
    sc.admission_type_group DESC;
