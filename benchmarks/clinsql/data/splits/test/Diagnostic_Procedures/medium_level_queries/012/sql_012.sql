WITH cohort_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 Day Stay'
        END AS stay_category
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 35 AND 45
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4111'))
            OR
            (d.icd_version = 10 AND (d.icd_code LIKE 'I20.0%' OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE 'I22%'))
        )
),
ultrasound_counts AS (
    SELECT
        ca.hadm_id,
        ca.subject_id,
        ca.stay_category,
        COUNT(proc.icd_code) AS ultrasound_count
    FROM
        cohort_admissions AS ca
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc ON ca.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND proc.icd_code = '8872')
            OR
            (proc.icd_version = 10 AND proc.icd_code LIKE 'B21%')
        )
    GROUP BY
        ca.hadm_id, ca.subject_id, ca.stay_category
)
SELECT
    uc.stay_category,
    COUNT(DISTINCT uc.subject_id) AS patient_count,
    ROUND(AVG(uc.ultrasound_count), 2) AS mean_ultrasounds_per_admission
FROM
    ultrasound_counts AS uc
GROUP BY
    uc.stay_category
ORDER BY
    uc.stay_category;
