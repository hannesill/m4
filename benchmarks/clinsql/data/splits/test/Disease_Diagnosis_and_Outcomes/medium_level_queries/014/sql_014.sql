WITH patient_base AS (
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
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
),

hf_admissions AS (
    SELECT DISTINCT
        pb.subject_id,
        pb.hadm_id,
        pb.admittime,
        pb.dischtime,
        pb.hospital_expire_flag,
        DATETIME_DIFF(pb.dischtime, pb.admittime, DAY) AS length_of_stay
    FROM
        patient_base AS pb
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON pb.hadm_id = d.hadm_id
    WHERE
        d.icd_code LIKE 'I50%'
        OR d.icd_code LIKE '428%'
),

admission_features AS (
    SELECT
        hfa.hadm_id,
        hfa.hospital_expire_flag,
        hfa.length_of_stay,
        CASE
            WHEN hfa.length_of_stay BETWEEN 1 AND 3 THEN '1-3 Days'
            WHEN hfa.length_of_stay BETWEEN 4 AND 7 THEN '4-7 Days'
            ELSE '>=8 Days'
        END AS los_category,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
                WHERE icu.hadm_id = hfa.hadm_id
                  AND DATETIME_DIFF(icu.intime, hfa.admittime, DAY) < 1
            ) THEN 'ICU on Day 1'
            ELSE 'No ICU on Day 1'
        END AS severity_group,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_ckd
                WHERE d_ckd.hadm_id = hfa.hadm_id
                  AND (d_ckd.icd_code LIKE 'N18%' OR d_ckd.icd_code LIKE '585%')
            ) THEN 1
            ELSE 0
        END AS has_ckd,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_dm
                WHERE d_dm.hadm_id = hfa.hadm_id
                  AND (d_dm.icd_code LIKE 'E10%' OR d_dm.icd_code LIKE 'E11%' OR d_dm.icd_code LIKE '250%')
            ) THEN 1
            ELSE 0
        END AS has_diabetes
    FROM
        hf_admissions AS hfa
)

SELECT
    severity_group,
    los_category,
    COUNT(*) AS total_admissions,
    SUM(hospital_expire_flag) AS total_deaths,
    ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_percent,
    APPROX_QUANTILES(length_of_stay, 2)[OFFSET(1)] AS median_los_days,
    ROUND(AVG(has_ckd) * 100, 2) AS ckd_prevalence_percent,
    ROUND(AVG(has_diabetes) * 100, 2) AS diabetes_prevalence_percent
FROM
    admission_features
WHERE
    length_of_stay >= 1
GROUP BY
    severity_group,
    los_category
ORDER BY
    severity_group DESC,
    CASE
        WHEN los_category = '1-3 Days' THEN 1
        WHEN los_category = '4-7 Days' THEN 2
        ELSE 3
    END;
