WITH
strata_grid AS (
    SELECT
        bleed_type,
        los_bucket,
        day_1_icu_status,
        los_order
    FROM
        (
            SELECT 'Upper GI Bleed' AS bleed_type UNION ALL
            SELECT 'Lower GI Bleed'
        ) AS bleed_types
    CROSS JOIN
        (
            SELECT '1-2 days' AS los_bucket, 1 AS los_order UNION ALL
            SELECT '3-5 days', 2 UNION ALL
            SELECT '6-9 days', 3 UNION ALL
            SELECT '>=10 days', 4
        ) AS los_buckets
    CROSS JOIN
        (
            SELECT 'Day-1 ICU' AS day_1_icu_status UNION ALL
            SELECT 'No Day-1 ICU'
        ) AS icu_statuses
),
cohort_data AS (
    WITH
    base_admissions AS (
        SELECT
            p.subject_id,
            a.hadm_id,
            a.admittime,
            a.dischtime,
            a.hospital_expire_flag
        FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
            ON a.subject_id = p.subject_id
        WHERE
            p.gender = 'F'
            AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 69 AND 79
    ),
    bleed_diagnoses AS (
        SELECT
            hadm_id,
            MAX(CASE
                WHEN icd_version = 9 AND (
                    icd_code IN ('5780', '5781', '5789', '4560', '45620', '5307') OR
                    SUBSTR(icd_code, 1, 4) IN ('5310', '5312', '5314', '5316', '5320', '5322', '5324', '5326',
                                              '5330', '5332', '5334', '5336', '5340', '5342', '5344', '5346')
                ) THEN 1
                WHEN icd_version = 10 AND (
                    icd_code IN ('K920', 'K921', 'K922', 'I8501', 'I8511', 'K223',
                                 'K250', 'K251', 'K252', 'K254', 'K256',
                                 'K260', 'K261', 'K262', 'K264', 'K266',
                                 'K270', 'K271', 'K272', 'K274', 'K276',
                                 'K280', 'K281', 'K282', 'K284', 'K286')
                ) THEN 1
                ELSE 0
            END) AS has_upper_bleed,
            MAX(CASE
                WHEN icd_version = 9 AND (
                    icd_code IN ('5693', '56202', '56203', '56212', '56213')
                ) THEN 1
                WHEN icd_version = 10 AND (
                    icd_code IN ('K625', 'K5701', 'K5711', 'K5721', 'K5731', 'K5741', 'K5751', 'K5781', 'K5791')
                ) THEN 1
                ELSE 0
            END) AS has_lower_bleed
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        GROUP BY hadm_id
    ),
    full_cohort AS (
        SELECT
            b.hadm_id,
            b.hospital_expire_flag,
            b.admittime,
            b.dischtime,
            CASE
                WHEN d.has_upper_bleed = 1 THEN 'Upper GI Bleed'
                WHEN d.has_lower_bleed = 1 THEN 'Lower GI Bleed'
            END AS bleed_type
        FROM base_admissions AS b
        INNER JOIN bleed_diagnoses AS d ON b.hadm_id = d.hadm_id
        WHERE d.has_upper_bleed = 1 OR d.has_lower_bleed = 1
    )
    SELECT
        c.hadm_id,
        c.bleed_type,
        c.hospital_expire_flag,
        CASE
            WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) BETWEEN 1 AND 2 THEN '1-2 days'
            WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) BETWEEN 3 AND 5 THEN '3-5 days'
            WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) BETWEEN 6 AND 9 THEN '6-9 days'
            WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) >= 10 THEN '>=10 days'
            ELSE NULL
        END AS los_bucket,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
                WHERE icu.hadm_id = c.hadm_id AND DATETIME_DIFF(icu.intime, c.admittime, HOUR) <= 24
            ) THEN 'Day-1 ICU'
            ELSE 'No Day-1 ICU'
        END AS day_1_icu_status,
        CAST(EXISTS (
            SELECT 1 FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
            WHERE icu.hadm_id = c.hadm_id
        ) AS INT64) AS any_icu_flag
    FROM full_cohort AS c
    WHERE DATETIME_DIFF(c.dischtime, c.admittime, DAY) >= 1
)
SELECT
    g.bleed_type,
    g.los_bucket,
    g.day_1_icu_status,
    COUNT(d.hadm_id) AS number_of_admissions,
    ROUND(SAFE_DIVIDE(SUM(d.hospital_expire_flag), COUNT(d.hadm_id)) * 100, 2) AS in_hospital_mortality_rate_pct,
    ROUND(SAFE_DIVIDE(SUM(d.any_icu_flag), COUNT(d.hadm_id)) * 100, 2) AS icu_admission_rate_pct
FROM strata_grid AS g
LEFT JOIN cohort_data AS d
    ON g.bleed_type = d.bleed_type
    AND g.los_bucket = d.los_bucket
    AND g.day_1_icu_status = d.day_1_icu_status
GROUP BY
    g.bleed_type,
    g.los_bucket,
    g.day_1_icu_status,
    g.los_order
ORDER BY
    g.bleed_type,
    g.los_order,
    g.day_1_icu_status DESC;
