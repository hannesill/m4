WITH hemorrhagic_stroke_admissions AS (
    SELECT DISTINCT
        adm.subject_id,
        adm.hadm_id,
        DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) as length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` pat
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` adm ON pat.subject_id = adm.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` dx ON adm.hadm_id = dx.hadm_id
    WHERE
        pat.gender = 'F'
        AND pat.anchor_age BETWEEN 80 AND 90
        AND adm.dischtime IS NOT NULL AND adm.admittime IS NOT NULL
        AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '430%') OR
            (dx.icd_version = 9 AND dx.icd_code LIKE '431%') OR
            (dx.icd_version = 9 AND dx.icd_code LIKE '432%') OR
            (dx.icd_version = 10 AND dx.icd_code LIKE 'I60%') OR
            (dx.icd_version = 10 AND dx.icd_code LIKE 'I61%') OR
            (dx.icd_version = 10 AND dx.icd_code LIKE 'I62%')
        )
),
admission_ultrasound_counts AS (
    SELECT
        hsa.hadm_id,
        CASE
            WHEN hsa.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Day Stay'
            WHEN hsa.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Day Stay'
        END as stay_category,
        COUNT(proc.icd_code) as ultrasound_count
    FROM
        hemorrhagic_stroke_admissions hsa
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` proc ON hsa.hadm_id = proc.hadm_id
        AND (
            (proc.icd_version = 9 AND proc.icd_code LIKE '88.7%') OR
            (proc.icd_version = 10 AND SUBSTR(proc.icd_code, 1, 1) = 'B' AND SUBSTR(proc.icd_code, 4, 1) = 'U')
        )
    WHERE hsa.length_of_stay BETWEEN 1 AND 7
    GROUP BY
        hsa.hadm_id, hsa.length_of_stay
)
SELECT
    stay_category,
    COUNT(hadm_id) as number_of_admissions,
    ROUND(AVG(ultrasound_count), 2) as mean_ultrasounds_per_admission,
    MIN(ultrasound_count) as min_ultrasounds_per_admission,
    MAX(ultrasound_count) as max_ultrasounds_per_admission
FROM
    admission_ultrasound_counts
GROUP BY
    stay_category
ORDER BY
    stay_category;
