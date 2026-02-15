WITH patient_cohort AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) as length_of_stay,
        MAX(CASE WHEN icu.stay_id IS NOT NULL THEN 1 ELSE 0 END) as had_icu_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 49 AND 59
        AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '428%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
        )
    GROUP BY
        a.hadm_id, a.dischtime, a.admittime
), imaging_counts AS (
    SELECT
        pc.hadm_id,
        CASE
            WHEN pc.length_of_stay BETWEEN 1 AND 4 THEN '1-4 Days'
            WHEN pc.length_of_stay BETWEEN 5 AND 7 THEN '5-7 Days'
        END AS los_group,
        CASE
            WHEN pc.had_icu_stay = 1 THEN 'ICU Stay'
            ELSE 'No ICU Stay'
        END AS icu_status,
        COUNT(pr.icd_code) AS imaging_count
    FROM
        patient_cohort AS pc
    LEFT JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS pr ON pc.hadm_id = pr.hadm_id
        AND (
            (pr.icd_version = 9 AND (
                pr.icd_code LIKE '88.0%' OR
                pr.icd_code LIKE '87.41%' OR
                pr.icd_code LIKE '87.71%' OR
                pr.icd_code LIKE '88.38%' OR
                pr.icd_code LIKE '88.9%'
            )) OR
            (pr.icd_version = 10 AND SUBSTR(pr.icd_code, 1, 1) = 'B' AND SUBSTR(pr.icd_code, 5, 1) IN ('2', '3', '4'))
        )
    WHERE
        pc.length_of_stay BETWEEN 1 AND 7
    GROUP BY
        pc.hadm_id, los_group, icu_status
)
SELECT
    los_group,
    icu_status,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(AVG(imaging_count), 2) AS mean_ct_mri_scans
FROM
    imaging_counts
GROUP BY
    los_group,
    icu_status
ORDER BY
    los_group,
    icu_status;
