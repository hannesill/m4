WITH
diagnoses_filtered AS (
    SELECT
        hadm_id,
        MAX(CASE
            WHEN icd_code LIKE 'E11%' THEN 1
            WHEN icd_version = 9 AND icd_code LIKE '250%' AND SUBSTR(icd_code, 5, 1) IN ('0', '2') THEN 1
            ELSE 0
        END) AS has_t2dm,
        MAX(CASE
            WHEN icd_code LIKE 'I50%' OR icd_code LIKE '428%' THEN 1
            ELSE 0
        END) AS has_hf
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
),
cohort_admissions AS (
    SELECT
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN diagnoses_filtered AS df
        ON a.hadm_id = df.hadm_id
    WHERE
        df.has_t2dm = 1
        AND df.has_hf = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 79 AND 89
        AND a.dischtime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 36
),
initiation_flags AS (
    SELECT
        ca.hadm_id,
        MAX(CASE
            WHEN rx.starttime BETWEEN ca.admittime AND DATETIME_ADD(ca.admittime, INTERVAL 12 HOUR) THEN 1
            ELSE 0
        END) AS was_initiated_early,
        MAX(CASE
            WHEN rx.starttime BETWEEN DATETIME_SUB(ca.dischtime, INTERVAL 24 HOUR) AND ca.dischtime THEN 1
            ELSE 0
        END) AS was_initiated_late
    FROM cohort_admissions AS ca
    LEFT JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
        ON ca.hadm_id = rx.hadm_id
        AND rx.starttime IS NOT NULL
        AND (
            LOWER(rx.drug) LIKE '%semaglutide%' OR LOWER(rx.drug) LIKE '%ozempic%' OR LOWER(rx.drug) LIKE '%rybelsus%' OR LOWER(rx.drug) LIKE '%wegovy%' OR
            LOWER(rx.drug) LIKE '%liraglutide%' OR LOWER(rx.drug) LIKE '%victoza%' OR LOWER(rx.drug) LIKE '%saxenda%' OR
            LOWER(rx.drug) LIKE '%dulaglutide%' OR LOWER(rx.drug) LIKE '%trulicity%' OR
            LOWER(rx.drug) LIKE '%exenatide%' OR LOWER(rx.drug) LIKE '%bydureon%' OR LOWER(rx.drug) LIKE '%byetta%' OR
            LOWER(rx.drug) LIKE '%lixisenatide%' OR LOWER(rx.drug) LIKE '%adlyxin%' OR
            LOWER(rx.drug) LIKE '%tirzepatide%' OR LOWER(rx.drug) LIKE '%mounjaro%'
        )
    GROUP BY
        ca.hadm_id
)
SELECT
    COUNT(hadm_id) AS total_cohort_admissions,
    SUM(was_initiated_early) AS early_window_initiations,
    SUM(was_initiated_late) AS late_window_initiations,
    ROUND(
        SUM(was_initiated_early) * 100.0 / NULLIF(COUNT(hadm_id), 0),
        2
    ) AS early_initiation_rate_pct,
    ROUND(
        SUM(was_initiated_late) * 100.0 / NULLIF(COUNT(hadm_id), 0),
        2
    ) AS late_initiation_rate_pct,
    ROUND(
        (SUM(was_initiated_late) * 100.0 / NULLIF(COUNT(hadm_id), 0)) -
        (SUM(was_initiated_early) * 100.0 / NULLIF(COUNT(hadm_id), 0)),
        2
    ) AS net_change_percentage_points
FROM initiation_flags;
