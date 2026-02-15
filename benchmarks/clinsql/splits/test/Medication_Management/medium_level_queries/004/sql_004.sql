WITH patient_cohort AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_dm ON a.hadm_id = d_dm.hadm_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 45 AND 55
        AND (d_dm.icd_code LIKE 'E11%' OR d_dm.icd_code LIKE '250%')
        AND (d_hf.icd_code LIKE 'I50%' OR d_hf.icd_code LIKE '428%')
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
),
glp1_prescriptions_by_period AS (
    SELECT
        cohort.hadm_id,
        MAX(CASE
            WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 72 THEN 1
            ELSE 0
        END) AS prescribed_in_early_72h,
        MAX(CASE
            WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48 THEN 1
            ELSE 0
        END) AS prescribed_in_late_48h
    FROM
        patient_cohort AS cohort
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
    WHERE
        rx.starttime IS NOT NULL
        AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
        AND (
               LOWER(rx.drug) LIKE '%semaglutide%'
            OR LOWER(rx.drug) LIKE '%liraglutide%'
            OR LOWER(rx.drug) LIKE '%dulaglutide%'
            OR LOWER(rx.drug) LIKE '%exenatide%'
            OR LOWER(rx.drug) LIKE '%lixisenatide%'
        )
    GROUP BY
        cohort.hadm_id
),
summary_stats AS (
    SELECT
        (SELECT COUNT(hadm_id) FROM patient_cohort) AS total_cohort_admissions,
        COUNTIF(prescribed_in_early_72h = 1) AS early_initiation_count,
        COUNTIF(prescribed_in_late_48h = 1) AS late_prevalence_count
    FROM
        patient_cohort
    LEFT JOIN
        glp1_prescriptions_by_period AS glp1
        ON patient_cohort.hadm_id = glp1.hadm_id
)
SELECT
    s.total_cohort_admissions,
    s.early_initiation_count,
    s.late_prevalence_count,
    ROUND((s.early_initiation_count * 100.0) / NULLIF(s.total_cohort_admissions, 0), 2) AS early_initiation_rate_pct,
    ROUND((s.late_prevalence_count * 100.0) / NULLIF(s.total_cohort_admissions, 0), 2) AS late_prevalence_rate_pct,
    ROUND(
        ((s.late_prevalence_count * 100.0) / NULLIF(s.total_cohort_admissions, 0)) -
        ((s.early_initiation_count * 100.0) / NULLIF(s.total_cohort_admissions, 0)),
    2) AS net_change_pp
FROM
    summary_stats AS s;
