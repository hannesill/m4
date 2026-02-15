WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.hospital_expire_flag,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) as length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 67 AND 77
),
diagnosed_cohort AS (
    SELECT
        pc.hadm_id,
        pc.admittime,
        pc.hospital_expire_flag,
        pc.length_of_stay,
        MAX(CASE
            WHEN d.icd_version = 9 AND d.icd_code IN ('42821', '42823', '42831', '42833', '42841', '42843') THEN 1
            WHEN d.icd_version = 10 AND d.icd_code IN ('I5021', 'I5023', 'I5031', 'I5033', 'I5041', 'I5043') THEN 1
            ELSE 0
        END) AS is_acute_hf,
        MAX(CASE
            WHEN d.icd_version = 9 AND d.icd_code LIKE '585%' THEN 1
            WHEN d.icd_version = 10 AND d.icd_code LIKE 'N18%' THEN 1
            ELSE 0
        END) AS has_ckd,
        MAX(CASE
            WHEN d.icd_version = 9 AND d.icd_code LIKE '250%' THEN 1
            WHEN d.icd_version = 10 AND (d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%') THEN 1
            ELSE 0
        END) AS has_diabetes
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON pc.hadm_id = d.hadm_id
    GROUP BY
        pc.hadm_id,
        pc.admittime,
        pc.hospital_expire_flag,
        pc.length_of_stay
),
stratified_cohort AS (
    SELECT
        dc.hospital_expire_flag,
        dc.has_ckd,
        dc.has_diabetes,
        CASE
            WHEN dc.length_of_stay <= 7 THEN '≤7 days'
            ELSE '>7 days'
        END AS los_group,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
                WHERE icu.hadm_id = dc.hadm_id
                  AND DATETIME_DIFF(icu.intime, dc.admittime, HOUR) <= 24
            ) THEN 'ICU on Day 1'
            ELSE 'Non-ICU on Day 1'
        END AS day1_icu_status
    FROM
        diagnosed_cohort AS dc
    WHERE
        dc.is_acute_hf = 1
)
SELECT
    los_group,
    day1_icu_status,
    COUNT(*) AS total_admissions,
    SUM(hospital_expire_flag) AS total_deaths,
    ROUND(100.0 * SUM(hospital_expire_flag) / COUNT(*), 2) AS mortality_rate_pct,
    ROUND(100.0 * SUM(has_ckd) / COUNT(*), 2) AS ckd_prevalence_pct,
    ROUND(100.0 * SUM(has_diabetes) / COUNT(*), 2) AS diabetes_prevalence_pct
FROM
    stratified_cohort
GROUP BY
    los_group,
    day1_icu_status
ORDER BY
    los_group,
    day1_icu_status;
