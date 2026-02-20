WITH all_admissions_with_age AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        p.gender,
        p.anchor_age,
        p.anchor_year,
        p.dod,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
),
diagnosis_flags AS (
    SELECT
        hadm_id,
        MAX(CASE
            WHEN (icd_version = 9 AND icd_code IN ('99592', '78552'))
              OR (icd_version = 10 AND icd_code IN ('R6521', 'A419'))
            THEN 1
            ELSE 0
        END) AS is_septic_shock,
        MAX(CASE
            WHEN (icd_version = 9 AND icd_code IN ('99592', '78552', '0389'))
              OR (icd_version = 10 AND icd_code IN ('R6521', 'R6881', 'R570', 'A419'))
            OR (icd_version = 9 AND (SUBSTR(icd_code, 1, 3) = '410' OR icd_code = '4275'))
              OR (icd_version = 10 AND (SUBSTR(icd_code, 1, 3) = 'I21' OR icd_code = 'I469'))
            OR (icd_version = 9 AND icd_code IN ('51881', '51882'))
              OR (icd_version = 10 AND icd_code IN ('J9600', 'J80'))
            OR (icd_version = 9 AND icd_code IN ('V5811', '78603'))
              OR (icd_version = 10 AND icd_code IN ('Z5111', 'R0603'))
            THEN 1
            ELSE 0
        END) AS is_major_complication,
        COUNT(DISTINCT icd_code) AS comorbidity_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
),
combined_data AS (
    SELECT
        aa.hadm_id,
        aa.subject_id,
        aa.gender,
        aa.age_at_admission,
        aa.hospital_expire_flag,
        COALESCE(df.is_septic_shock, 0) AS is_septic_shock,
        COALESCE(df.is_major_complication, 0) AS is_major_complication,
        COALESCE(df.comorbidity_count, 0) AS comorbidity_count,
        DATETIME_DIFF(aa.dischtime, aa.admittime, DAY) AS los_days,
        CASE
            WHEN aa.dod IS NOT NULL AND aa.dischtime IS NOT NULL AND aa.dod <= DATETIME_ADD(aa.dischtime, INTERVAL 90 DAY)
            THEN 1
            ELSE 0
        END AS is_dead_within_90_days,
        LEAST(100, (aa.age_at_admission * 0.5) + (COALESCE(df.comorbidity_count, 0) * 2.5)) AS risk_score
    FROM
        all_admissions_with_age AS aa
    LEFT JOIN
        diagnosis_flags AS df
        ON aa.hadm_id = df.hadm_id
),
cohort_definitions AS (
    SELECT
        *,
        CASE
            WHEN gender = 'M'
                AND age_at_admission BETWEEN 63 AND 73
                AND is_septic_shock = 1
                AND comorbidity_count > 15
            THEN 'Target Cohort (Male, 63-73, Septic Shock, High Comorbidity)'
            ELSE 'General Inpatient Population'
        END AS cohort_group
    FROM
        combined_data
),
summary_stats AS (
    SELECT
        cohort_group,
        COUNT(DISTINCT hadm_id) AS total_admissions,
        ROUND(AVG(risk_score), 2) AS mean_risk_score,
        ROUND(SAFE_DIVIDE(SUM(is_dead_within_90_days), COUNT(hadm_id)) * 100, 2) AS mortality_rate_90_day_pct,
        ROUND(SAFE_DIVIDE(SUM(is_major_complication), COUNT(hadm_id)) * 100, 2) AS major_complication_rate_pct,
        ROUND(AVG(CASE WHEN hospital_expire_flag = 0 THEN los_days ELSE NULL END), 2) AS avg_survivor_los_days
    FROM
        cohort_definitions
    GROUP BY
        cohort_group
),
profile_percentile AS (
    SELECT
        ROUND(PERCENT_RANK() OVER (ORDER BY risk_score) * 100, 2) AS percentile
    FROM
        cohort_definitions
    WHERE
        cohort_group = 'Target Cohort (Male, 63-73, Septic Shock, High Comorbidity)'
    QUALIFY risk_score = 74
    LIMIT 1
)
SELECT
    s.cohort_group,
    s.total_admissions,
    s.mean_risk_score,
    s.mortality_rate_90_day_pct,
    s.major_complication_rate_pct,
    s.avg_survivor_los_days,
    NULL AS profile_risk_percentile
FROM
    summary_stats AS s
UNION ALL
SELECT
    'Profile (68M, Septic Shock, High Comorbidity) Risk Percentile' AS cohort_group,
    NULL AS total_admissions,
    74.00 AS mean_risk_score,
    NULL AS mortality_rate_90_day_pct,
    NULL AS major_complication_rate_pct,
    NULL AS avg_survivor_los_days,
    p.percentile AS profile_risk_percentile
FROM
    profile_percentile AS p;
