WITH sepsis_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 4 THEN '1-4 Days'
            ELSE '5-8 Days'
        END AS los_group
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
            ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 48 AND 58
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 8
    GROUP BY
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime
    HAVING
        COUNT(CASE WHEN d.icd_code IN ('99591', 'A419', 'R6520') THEN 1 END) > 0
        AND COUNT(CASE WHEN d.icd_code IN ('78552', 'R6521') THEN 1 END) = 0
),
procedure_and_icu_data AS (
    SELECT
        sc.subject_id,
        sc.hadm_id,
        sc.los_group,
        COUNT(DISTINCT proc.seq_num) AS ultrasound_count,
        CASE WHEN COUNT(DISTINCT icu.stay_id) > 0 THEN 'ICU Stay' ELSE 'No ICU Stay' END AS icu_status
    FROM
        sepsis_cohort AS sc
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
            ON sc.hadm_id = proc.hadm_id
            AND proc.icd_version = 9 AND proc.icd_code LIKE '887%'
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu
            ON sc.hadm_id = icu.hadm_id
    GROUP BY
        sc.subject_id,
        sc.hadm_id,
        sc.los_group
)
SELECT
    p.los_group,
    p.icu_status,
    COUNT(DISTINCT p.subject_id) AS patient_count,
    ROUND(AVG(p.ultrasound_count), 2) AS avg_ultrasounds_per_admission
FROM
    procedure_and_icu_data AS p
GROUP BY
    p.los_group,
    p.icu_status
ORDER BY
    p.los_group,
    p.icu_status DESC;
