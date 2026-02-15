WITH septic_shock_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        CASE
            WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 days'
            ELSE '4-7 days'
        END AS stay_category,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
                WHERE icu.hadm_id = a.hadm_id
            ) THEN 'ICU Stay'
            ELSE 'No ICU Stay'
        END AS icu_status
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 57 AND 67
        AND d.icd_code IN ('78552', 'R6521')
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
),
ultrasound_counts AS (
    SELECT
        ssa.hadm_id,
        ssa.stay_category,
        ssa.icu_status,
        COUNT(pr.icd_code) AS ultrasound_count
    FROM septic_shock_admissions ssa
    LEFT JOIN `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr
        ON ssa.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '887%')
            OR (pr.icd_version = 10 AND pr.icd_code LIKE 'B__4%')
        )
    GROUP BY
        ssa.hadm_id, ssa.stay_category, ssa.icu_status
)
SELECT
    uc.stay_category,
    uc.icu_status,
    COUNT(uc.hadm_id) AS total_admissions,
    APPROX_QUANTILES(uc.ultrasound_count, 4)[OFFSET(1)] AS p25_ultrasounds,
    APPROX_QUANTILES(uc.ultrasound_count, 4)[OFFSET(2)] AS p50_ultrasounds,
    APPROX_QUANTILES(uc.ultrasound_count, 4)[OFFSET(3)] AS p75_ultrasounds
FROM ultrasound_counts uc
GROUP BY
    uc.stay_category,
    uc.icu_status
ORDER BY
    uc.stay_category,
    uc.icu_status;
