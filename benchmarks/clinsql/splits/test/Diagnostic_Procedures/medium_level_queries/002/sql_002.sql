WITH tia_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 64 AND 74
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '435%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
        )
        AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) BETWEEN 1 AND 7
),
admission_details AS (
    SELECT
        tia.hadm_id,
        CASE
            WHEN DATETIME_DIFF(tia.dischtime, tia.admittime, DAY) BETWEEN 1 AND 3 THEN '1-3 Day Stay'
            ELSE '4-7 Day Stay'
        END AS stay_category,
        CASE
            WHEN icu.hadm_id IS NOT NULL THEN 'ICU Admission'
            ELSE 'No ICU Admission'
        END AS icu_status,
        COUNT(pr.icd_code) AS ultrasound_count
    FROM
        tia_admissions AS tia
    LEFT JOIN
        (SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
        ON tia.hadm_id = icu.hadm_id
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr
        ON tia.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND pr.icd_code LIKE '88.7%')
            OR (pr.icd_version = 10 AND SUBSTR(pr.icd_code, 1, 1) = 'B' AND SUBSTR(pr.icd_code, 5, 1) = '4')
        )
    GROUP BY
        tia.hadm_id, tia.admittime, tia.dischtime, icu.hadm_id
)
SELECT
    stay_category,
    icu_status,
    COUNT(hadm_id) AS total_admissions,
    ROUND(AVG(ultrasound_count), 2) AS avg_ultrasounds_per_admission,
    MIN(ultrasound_count) AS min_ultrasounds,
    MAX(ultrasound_count) AS max_ultrasounds
FROM
    admission_details
GROUP BY
    stay_category,
    icu_status
ORDER BY
    stay_category,
    icu_status;
