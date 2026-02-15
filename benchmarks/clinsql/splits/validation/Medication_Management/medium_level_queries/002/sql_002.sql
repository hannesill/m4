WITH patient_cohort AS (
    SELECT DISTINCT
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 59 AND 69
        AND (d_diabetes.icd_code LIKE 'E11%' OR d_diabetes.icd_code LIKE '250%')
        AND (d_hf.icd_code LIKE 'I50%' OR d_hf.icd_code LIKE '428%')
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
),
admission_prescription_summary AS (
    SELECT
        cohort.hadm_id,
        MAX(CASE
            WHEN DATETIME_DIFF(rx.starttime, cohort.admittime, HOUR) BETWEEN 0 AND 48 THEN 1
            ELSE 0
        END) AS prescribed_in_first_48h,
        MAX(CASE
            WHEN DATETIME_DIFF(cohort.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12 THEN 1
            ELSE 0
        END) AS prescribed_in_last_12h
    FROM
        patient_cohort AS cohort
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
    WHERE
        LOWER(rx.drug) IN (
            'liraglutide', 'victoza',
            'semaglutide', 'ozempic', 'rybelsus',
            'dulaglutide', 'trulicity',
            'exenatide', 'byetta', 'bydureon',
            'lixisenatide', 'adlyxin'
        )
        AND rx.starttime IS NOT NULL
    GROUP BY
        cohort.hadm_id
)
SELECT
    COUNT(DISTINCT cohort.hadm_id) AS total_admissions_in_cohort,
    SUM(COALESCE(summary.prescribed_in_first_48h, 0)) AS admissions_with_glp1_first_48h,
    SUM(COALESCE(summary.prescribed_in_last_12h, 0)) AS admissions_with_glp1_last_12h,
    ROUND(
        (SUM(COALESCE(summary.prescribed_in_first_48h, 0)) * 100.0)
        / NULLIF(COUNT(DISTINCT cohort.hadm_id), 0),
        2
    ) AS prevalence_pct_first_48h,
    ROUND(
        (SUM(COALESCE(summary.prescribed_in_last_12h, 0)) * 100.0)
        / NULLIF(COUNT(DISTINCT cohort.hadm_id), 0),
        2
    ) AS prevalence_pct_last_12h,
    ROUND(
        (
            (SUM(COALESCE(summary.prescribed_in_first_48h, 0)) * 100.0)
            / NULLIF(COUNT(DISTINCT cohort.hadm_id), 0)
        ) - (
            (SUM(COALESCE(summary.prescribed_in_last_12h, 0)) * 100.0)
            / NULLIF(COUNT(DISTINCT cohort.hadm_id), 0)
        ),
        2
    ) AS absolute_difference_pp
FROM
    patient_cohort AS cohort
LEFT JOIN
    admission_prescription_summary AS summary ON cohort.hadm_id = summary.hadm_id;
