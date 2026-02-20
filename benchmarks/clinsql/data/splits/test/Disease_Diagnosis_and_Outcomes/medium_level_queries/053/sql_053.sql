WITH
base_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
),
pneumonia_admissions AS (
    SELECT
        bc.subject_id,
        bc.hadm_id,
        bc.admittime,
        bc.dischtime,
        bc.hospital_expire_flag,
        CASE
            WHEN MAX(CASE WHEN (d.icd_code = '5070' AND d.icd_version = 9) OR (d.icd_code = 'J690' AND d.icd_version = 10) THEN 1 ELSE 0 END) = 1
                THEN 'Aspiration Pneumonia'
            ELSE 'Community-Acquired Pneumonia'
        END AS pneumonia_type
    FROM
        base_cohort AS bc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON bc.hadm_id = d.hadm_id
    WHERE
        (d.icd_code = '486' AND d.icd_version = 9)
        OR (d.icd_code LIKE 'J18%' AND d.icd_version = 10)
        OR (d.icd_code = '5070' AND d.icd_version = 9)
        OR (d.icd_code = 'J690' AND d.icd_version = 10)
    GROUP BY
        bc.subject_id,
        bc.hadm_id,
        bc.admittime,
        bc.dischtime,
        bc.hospital_expire_flag
),
comorbidity_counts AS (
    SELECT
        pa.hadm_id,
        COUNT(DISTINCT d.icd_code) AS total_diagnoses
    FROM
        pneumonia_admissions AS pa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON pa.hadm_id = d.hadm_id
    GROUP BY
        pa.hadm_id
),
final_cohort AS (
    SELECT
        pa.hadm_id,
        pa.pneumonia_type,
        pa.hospital_expire_flag,
        cc.total_diagnoses,
        DATETIME_DIFF(pa.dischtime, pa.admittime, DAY) AS los_days,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
                WHERE icu.hadm_id = pa.hadm_id
                  AND icu.intime <= DATETIME_ADD(pa.admittime, INTERVAL 24 HOUR)
            ) THEN 'Day-1 ICU'
            ELSE 'No Day-1 ICU'
        END AS day1_icu_status
    FROM
        pneumonia_admissions AS pa
    INNER JOIN
        comorbidity_counts AS cc ON pa.hadm_id = cc.hadm_id
),
strata_scaffold AS (
    SELECT
        pneumonia_type,
        day1_icu_status,
        los_bucket,
        los_bucket_sort_order
    FROM
        (SELECT 'Community-Acquired Pneumonia' AS pneumonia_type UNION ALL SELECT 'Aspiration Pneumonia')
    CROSS JOIN
        (SELECT 'Day-1 ICU' AS day1_icu_status UNION ALL SELECT 'No Day-1 ICU')
    CROSS JOIN
        (
            SELECT '1-3 days' AS los_bucket, 1 AS los_bucket_sort_order UNION ALL
            SELECT '4-7 days' AS los_bucket, 2 AS los_bucket_sort_order UNION ALL
            SELECT '>=8 days' AS los_bucket, 3 AS los_bucket_sort_order
        )
),
grouped_stats AS (
    SELECT
        pneumonia_type,
        day1_icu_status,
        CASE
            WHEN los_days BETWEEN 1 AND 3 THEN '1-3 days'
            WHEN los_days BETWEEN 4 AND 7 THEN '4-7 days'
            WHEN los_days >= 8 THEN '>=8 days'
        END AS los_bucket,
        COUNT(DISTINCT hadm_id) AS patient_count,
        ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
        ROUND(AVG(total_diagnoses), 2) AS avg_comorbidity_count
    FROM
        final_cohort
    WHERE los_days >= 1
    GROUP BY
        pneumonia_type,
        day1_icu_status,
        los_bucket
)
SELECT
    s.pneumonia_type,
    s.day1_icu_status,
    s.los_bucket,
    COALESCE(gs.patient_count, 0) AS patient_count,
    gs.mortality_rate_pct,
    gs.avg_comorbidity_count,
    ROUND(
        gs.mortality_rate_pct - LAG(gs.mortality_rate_pct, 1) OVER (PARTITION BY s.pneumonia_type, s.day1_icu_status ORDER BY s.los_bucket_sort_order),
        2
    ) AS absolute_mortality_difference_vs_prev_los_bucket,
    ROUND(
        SAFE_DIVIDE(
            gs.mortality_rate_pct - LAG(gs.mortality_rate_pct, 1) OVER (PARTITION BY s.pneumonia_type, s.day1_icu_status ORDER BY s.los_bucket_sort_order),
            LAG(gs.mortality_rate_pct, 1) OVER (PARTITION BY s.pneumonia_type, s.day1_icu_status ORDER BY s.los_bucket_sort_order)
        ) * 100,
        2
    ) AS relative_mortality_difference_vs_prev_los_bucket_pct
FROM
    strata_scaffold AS s
LEFT JOIN
    grouped_stats AS gs
    ON s.pneumonia_type = gs.pneumonia_type
    AND s.day1_icu_status = gs.day1_icu_status
    AND s.los_bucket = gs.los_bucket
ORDER BY
    s.pneumonia_type,
    s.day1_icu_status,
    s.los_bucket_sort_order;
