WITH patient_cohort AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id,
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
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 48 AND 58
        AND (
            d_diabetes.icd_code LIKE 'E11%'
            OR (d_diabetes.icd_version = 9 AND d_diabetes.icd_code LIKE '250.__' AND SUBSTR(d_diabetes.icd_code, 5, 1) IN ('0', '2'))
        )
        AND (
            d_hf.icd_code LIKE 'I50%'
            OR d_hf.icd_code LIKE '428%'
        )
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 24
),

patient_level_flags AS (
    SELECT
        c.hadm_id,
        c.subject_id,
        MAX(CASE
            WHEN
                rx.hadm_id IS NOT NULL
                AND DATETIME_DIFF(rx.starttime, c.admittime, HOUR) >= 0
                AND DATETIME_DIFF(rx.starttime, c.admittime, HOUR) < 12
            THEN 1
            ELSE 0
        END) AS received_glp1_early,
        MAX(CASE
            WHEN
                rx.hadm_id IS NOT NULL
                AND DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) >= 0
                AND DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) < 12
            THEN 1
            ELSE 0
        END) AS received_glp1_late
    FROM
        patient_cohort AS c
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
            ON c.hadm_id = rx.hadm_id
            AND (
                LOWER(rx.drug) LIKE '%liraglutide%'
                OR LOWER(rx.drug) LIKE '%semaglutide%'
                OR LOWER(rx.drug) LIKE '%dulaglutide%'
                OR LOWER(rx.drug) LIKE '%exenatide%'
                OR LOWER(rx.drug) LIKE '%lixisenatide%'
            )
            AND rx.starttime IS NOT NULL
    GROUP BY
        c.hadm_id, c.subject_id
)

SELECT
    COUNT(hadm_id) AS total_patients_in_cohort,
    SUM(received_glp1_early) AS patients_on_glp1_early,
    SUM(received_glp1_late) AS patients_on_glp1_late,
    ROUND(SUM(received_glp1_early) * 100.0 / COUNT(hadm_id), 2) AS prevalence_rate_early_pct,
    ROUND(SUM(received_glp1_late) * 100.0 / COUNT(hadm_id), 2) AS prevalence_rate_late_pct,
    ROUND(
        (SUM(received_glp1_late) * 100.0 / COUNT(hadm_id)) -
        (SUM(received_glp1_early) * 100.0 / COUNT(hadm_id)),
    2) AS net_change_percentage_points
FROM
    patient_level_flags;
