WITH
admissions_base AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
),
mi_diagnoses AS (
    SELECT
        hadm_id,
        CASE
            WHEN MAX(CASE
                WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 4) IN ('4100', '4101', '4102', '4103', '4104', '4105', '4106', '4108'))
                  OR (icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('I210', 'I211', 'I212', 'I213'))
                THEN 1 ELSE 0 END) = 1 THEN 'STEMI'
            WHEN MAX(CASE
                WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 4) = '4107')
                  OR (icd_version = 10 AND SUBSTR(icd_code, 1, 4) = 'I214')
                THEN 1 ELSE 0 END) = 1 THEN 'NSTEMI'
        END AS mi_type
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
        OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I21')
    GROUP BY
        hadm_id
),
comorbid_counts AS (
    SELECT
        hadm_id,
        MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '585') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'N18') THEN 1 ELSE 0 END) AS has_ckd,
        MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '250') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E13')) THEN 1 ELSE 0 END) AS has_diabetes,
        (
            MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '428') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I50') THEN 1 ELSE 0 END) +
            MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '585') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'N18') THEN 1 ELSE 0 END) +
            MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '250') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E13')) THEN 1 ELSE 0 END) +
            MAX(CASE WHEN (icd_version = 9 AND icd_code = '42731') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I48') THEN 1 ELSE 0 END) +
            MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '401') OR (icd_version = 10 AND icd_code = 'I10') THEN 1 ELSE 0 END) +
            MAX(CASE WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432', '433', '434')) OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62', 'I63')) THEN 1 ELSE 0 END) +
            MAX(CASE WHEN (icd_version = 9 AND icd_code = '486') OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'J18') THEN 1 ELSE 0 END)
        ) AS comorbid_system_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
),
final_cohort AS (
    SELECT
        ab.hadm_id,
        ab.hospital_expire_flag,
        mi.mi_type,
        COALESCE(cc.has_ckd, 0) AS has_ckd,
        COALESCE(cc.has_diabetes, 0) AS has_diabetes,
        CASE
            WHEN DATETIME_DIFF(ab.dischtime, ab.admittime, DAY) BETWEEN 1 AND 2 THEN '1-2 days'
            WHEN DATETIME_DIFF(ab.dischtime, ab.admittime, DAY) BETWEEN 3 AND 5 THEN '3-5 days'
            WHEN DATETIME_DIFF(ab.dischtime, ab.admittime, DAY) BETWEEN 6 AND 9 THEN '6-9 days'
            WHEN DATETIME_DIFF(ab.dischtime, ab.admittime, DAY) >= 10 THEN '>=10 days'
            ELSE NULL
        END AS los_bin,
        CASE
            WHEN COALESCE(cc.comorbid_system_count, 0) <= 1 THEN '0-1'
            WHEN COALESCE(cc.comorbid_system_count, 0) = 2 THEN '2'
            WHEN COALESCE(cc.comorbid_system_count, 0) >= 3 THEN '>=3'
            ELSE NULL
        END AS comorbid_bin
    FROM
        admissions_base AS ab
    INNER JOIN
        mi_diagnoses AS mi ON ab.hadm_id = mi.hadm_id
    LEFT JOIN
        comorbid_counts AS cc ON ab.hadm_id = cc.hadm_id
    WHERE
        ab.age_at_admission BETWEEN 51 AND 61
        AND mi.mi_type IS NOT NULL
        AND DATETIME_DIFF(ab.dischtime, ab.admittime, DAY) >= 1
),
strata_scaffold AS (
    SELECT
        mi_type,
        los_bin,
        comorbid_bin,
        los_order,
        comorbid_order
    FROM
        (SELECT 'STEMI' AS mi_type UNION ALL SELECT 'NSTEMI' AS mi_type)
    CROSS JOIN
        (
            SELECT '1-2 days' AS los_bin, 1 AS los_order UNION ALL
            SELECT '3-5 days' AS los_bin, 2 AS los_order UNION ALL
            SELECT '6-9 days' AS los_bin, 3 AS los_order UNION ALL
            SELECT '>=10 days' AS los_bin, 4 AS los_order
        )
    CROSS JOIN
        (
            SELECT '0-1' AS comorbid_bin, 1 AS comorbid_order UNION ALL
            SELECT '2' AS comorbid_bin, 2 AS comorbid_order UNION ALL
            SELECT '>=3' AS comorbid_bin, 3 AS comorbid_order
        )
)
SELECT
    s.mi_type,
    s.los_bin,
    s.comorbid_bin AS num_major_comorbid_systems,
    COUNT(fc.hadm_id) AS N,
    ROUND(SAFE_DIVIDE(SUM(fc.hospital_expire_flag), COUNT(fc.hadm_id)) * 100, 2) AS mortality_rate_pct,
    ROUND(SAFE_DIVIDE(SUM(fc.has_ckd), COUNT(fc.hadm_id)) * 100, 2) AS ckd_prevalence_pct,
    ROUND(SAFE_DIVIDE(SUM(fc.has_diabetes), COUNT(fc.hadm_id)) * 100, 2) AS diabetes_prevalence_pct
FROM
    strata_scaffold AS s
LEFT JOIN
    final_cohort AS fc
    ON s.mi_type = fc.mi_type
    AND s.los_bin = fc.los_bin
    AND s.comorbid_bin = fc.comorbid_bin
GROUP BY
    s.mi_type,
    s.los_bin,
    s.comorbid_bin,
    s.los_order,
    s.comorbid_order
ORDER BY
    s.mi_type,
    s.los_order,
    s.comorbid_order;
