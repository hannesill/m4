WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 52 AND 62
        AND a.admittime IS NOT NULL AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code LIKE 'E11%'
                OR d.icd_code LIKE '250%'
            )
        )
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code LIKE 'I50%'
                OR d.icd_code LIKE '428%'
            )
        )
),
glp1_events AS (
    SELECT
        pc.hadm_id,
        MAX(CASE
            WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 24 THEN 1
            ELSE 0
        END) AS given_in_first_24h,
        MAX(CASE
            WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48 THEN 1
            ELSE 0
        END) AS given_in_last_48h
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON pc.hadm_id = rx.hadm_id
    WHERE
        rx.starttime BETWEEN pc.admittime AND pc.dischtime
        AND (
            LOWER(rx.drug) LIKE '%semaglutide%'
            OR LOWER(rx.drug) LIKE '%liraglutide%'
            OR LOWER(rx.drug) LIKE '%dulaglutide%'
            OR LOWER(rx.drug) LIKE '%exenatide%'
            OR LOWER(rx.drug) LIKE '%lixisenatide%'
        )
        AND LOWER(rx.route) = 'sc'
    GROUP BY
        pc.hadm_id
),
summary_stats AS (
    SELECT
        COUNT(DISTINCT pc.hadm_id) AS total_cohort_admissions,
        COUNT(DISTINCT CASE WHEN ge.given_in_first_24h = 1 THEN ge.hadm_id END) AS early_window_admissions,
        COUNT(DISTINCT CASE WHEN ge.given_in_last_48h = 1 THEN ge.hadm_id END) AS late_window_admissions
    FROM
        patient_cohort AS pc
    LEFT JOIN
        glp1_events AS ge ON pc.hadm_id = ge.hadm_id
)
SELECT
    s.total_cohort_admissions,
    s.early_window_admissions,
    s.late_window_admissions,
    ROUND(SAFE_DIVIDE(s.early_window_admissions * 100.0, s.total_cohort_admissions), 2) AS prevalence_first_24h_pct,
    ROUND(SAFE_DIVIDE(s.late_window_admissions * 100.0, s.total_cohort_admissions), 2) AS prevalence_last_48h_pct,
    ROUND(
        (SAFE_DIVIDE(s.late_window_admissions * 100.0, s.total_cohort_admissions)) -
        (SAFE_DIVIDE(s.early_window_admissions * 100.0, s.total_cohort_admissions)),
    2) AS absolute_change_in_prevalence_pct,
    ROUND(
        SAFE_DIVIDE(
            (SAFE_DIVIDE(s.late_window_admissions * 100.0, s.total_cohort_admissions)) -
            (SAFE_DIVIDE(s.early_window_admissions * 100.0, s.total_cohort_admissions)),
            SAFE_DIVIDE(s.early_window_admissions * 100.0, s.total_cohort_admissions)
        ) * 100.0,
    2) AS relative_change_in_prevalence_pct
FROM
    summary_stats s;
