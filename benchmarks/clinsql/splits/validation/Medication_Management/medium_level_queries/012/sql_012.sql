WITH cohort_admissions AS (
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
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes ON a.hadm_id = d_diabetes.hadm_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
        AND (
            d_diabetes.icd_code LIKE 'E11%'
            OR (d_diabetes.icd_version = 9 AND SUBSTR(d_diabetes.icd_code, 1, 3) = '250' AND SUBSTR(d_diabetes.icd_code, 5, 1) IN ('0', '2'))
        )
        AND (
            d_hf.icd_code LIKE 'I50%'
            OR d_hf.icd_code LIKE '428%'
        )
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
)
SELECT
    COUNT(DISTINCT c.hadm_id) AS total_cohort_admissions,
    COUNT(DISTINCT CASE
        WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) < 12 THEN c.hadm_id
        ELSE NULL
    END) AS patients_early_initiation,
    COUNT(DISTINCT CASE
        WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 72 AND rx.starttime IS NOT NULL THEN c.hadm_id
        ELSE NULL
    END) AS patients_late_prevalence,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) < 12 THEN c.hadm_id
            ELSE NULL
        END) * 100.0 / NULLIF(COUNT(DISTINCT c.hadm_id), 0),
    2) AS early_initiation_rate_pct,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 72 AND rx.starttime IS NOT NULL THEN c.hadm_id
            ELSE NULL
        END) * 100.0 / NULLIF(COUNT(DISTINCT c.hadm_id), 0),
    2) AS late_prevalence_rate_pct,
    (
        ROUND(
            COUNT(DISTINCT CASE
                WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 72 AND rx.starttime IS NOT NULL THEN c.hadm_id
                ELSE NULL
            END) * 100.0 / NULLIF(COUNT(DISTINCT c.hadm_id), 0),
        2)
        -
        ROUND(
            COUNT(DISTINCT CASE
                WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) < 12 THEN c.hadm_id
                ELSE NULL
            END) * 100.0 / NULLIF(COUNT(DISTINCT c.hadm_id), 0),
        2)
    ) AS net_change_percentage_points
FROM
    cohort_admissions AS c
LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
    ON c.hadm_id = rx.hadm_id
    AND (
        LOWER(rx.drug) LIKE '%liraglutide%'
        OR LOWER(rx.drug) LIKE '%semaglutide%'
        OR LOWER(rx.drug) LIKE '%dulaglutide%'
        OR LOWER(rx.drug) LIKE '%exenatide%'
        OR LOWER(rx.drug) LIKE '%victoza%'
        OR LOWER(rx.drug) LIKE '%ozempic%'
        OR LOWER(rx.drug) LIKE '%trulicity%'
        OR LOWER(rx.drug) LIKE '%byetta%'
    )
    AND rx.starttime IS NOT NULL
    AND rx.starttime BETWEEN c.admittime AND c.dischtime;
