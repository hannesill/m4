WITH patient_cohort AS (
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
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 51 AND 61
        AND (
            d_diabetes.icd_code LIKE '250%'
            OR d_diabetes.icd_code LIKE 'E10%'
            OR d_diabetes.icd_code LIKE 'E11%'
        )
        AND (
            d_hf.icd_code LIKE '428%'
            OR d_hf.icd_code LIKE 'I50%'
        )
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 36
),

insulin_prescriptions AS (
    SELECT
        cohort.hadm_id,
        CASE
            WHEN LOWER(rx.drug) LIKE '%glargine%' OR LOWER(rx.drug) LIKE '%lantus%'
                 OR LOWER(rx.drug) LIKE '%detemir%' OR LOWER(rx.drug) LIKE '%levemir%'
                 OR LOWER(rx.drug) LIKE '%degludec%' OR LOWER(rx.drug) LIKE '%toujeo%'
                 OR LOWER(rx.drug) LIKE '%tresiba%'
            THEN 'Basal'
            WHEN LOWER(rx.drug) LIKE '%aspart%' OR LOWER(rx.drug) LIKE '%novolog%'
                 OR LOWER(rx.drug) LIKE '%lispro%' OR LOWER(rx.drug) LIKE '%humalog%'
                 OR LOWER(rx.drug) LIKE '%regular%' OR LOWER(rx.drug) LIKE '%apidra%'
                 OR LOWER(rx.drug) LIKE '%glulisine%'
            THEN 'Bolus'
            WHEN LOWER(rx.drug) LIKE '%sliding scale%'
            THEN 'Sliding_Scale'
            ELSE NULL
        END AS insulin_category,
        (rx.starttime <= DATETIME_ADD(cohort.admittime, INTERVAL 24 HOUR)) AS is_early_period,
        (rx.starttime >= DATETIME_SUB(cohort.dischtime, INTERVAL 12 HOUR)) AS is_late_period
    FROM
        patient_cohort AS cohort
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON cohort.hadm_id = rx.hadm_id
    WHERE
        rx.starttime IS NOT NULL
        AND rx.starttime BETWEEN cohort.admittime AND cohort.dischtime
        AND LOWER(rx.drug) LIKE '%insulin%'
),

patient_regimen_flags AS (
    SELECT
        hadm_id,
        LOGICAL_OR(is_early_period AND insulin_category = 'Basal') AS has_basal_early,
        LOGICAL_OR(is_early_period AND insulin_category = 'Bolus') AS has_bolus_early,
        LOGICAL_OR(is_early_period AND insulin_category = 'Sliding_Scale') AS has_ssi_early,
        LOGICAL_OR(is_late_period AND insulin_category = 'Basal') AS has_basal_late,
        LOGICAL_OR(is_late_period AND insulin_category = 'Bolus') AS has_bolus_late,
        LOGICAL_OR(is_late_period AND insulin_category = 'Sliding_Scale') AS has_ssi_late
    FROM
        insulin_prescriptions
    GROUP BY
        hadm_id
),

regimen_classification AS (
    SELECT
        hadm_id,
        CASE
            WHEN has_basal_early AND has_bolus_early THEN 'Basal-Bolus'
            WHEN has_basal_early THEN 'Basal'
            WHEN has_bolus_early THEN 'Bolus'
            WHEN has_ssi_early THEN 'Sliding-Scale'
            ELSE NULL
        END AS early_regimen,
        CASE
            WHEN has_basal_late AND has_bolus_late THEN 'Basal-Bolus'
            WHEN has_basal_late THEN 'Basal'
            WHEN has_bolus_late THEN 'Bolus'
            WHEN has_ssi_late THEN 'Sliding-Scale'
            ELSE NULL
        END AS late_regimen
    FROM
        patient_regimen_flags
),

regimen_counts AS (
    SELECT
        'Basal-Bolus' AS regimen_type,
        COUNTIF(early_regimen = 'Basal-Bolus') AS early_count,
        COUNTIF(late_regimen = 'Basal-Bolus') AS late_count
    FROM regimen_classification
    UNION ALL
    SELECT
        'Basal' AS regimen_type,
        COUNTIF(early_regimen = 'Basal') AS early_count,
        COUNTIF(late_regimen = 'Basal') AS late_count
    FROM regimen_classification
    UNION ALL
    SELECT
        'Bolus' AS regimen_type,
        COUNTIF(early_regimen = 'Bolus') AS early_count,
        COUNTIF(late_regimen = 'Bolus') AS late_count
    FROM regimen_classification
    UNION ALL
    SELECT
        'Sliding-Scale' AS regimen_type,
        COUNTIF(early_regimen = 'Sliding-Scale') AS early_count,
        COUNTIF(late_regimen = 'Sliding-Scale') AS late_count
    FROM regimen_classification
),

total_cohort AS (
    SELECT COUNT(DISTINCT hadm_id) AS total_patients FROM patient_cohort
)

SELECT
    rc.regimen_type,
    ROUND(rc.early_count * 100.0 / tc.total_patients, 1) AS prevalence_early_24h_pct,
    ROUND(rc.late_count * 100.0 / tc.total_patients, 1) AS prevalence_late_12h_pct,
    ROUND((rc.late_count * 100.0 / tc.total_patients) - (rc.early_count * 100.0 / tc.total_patients), 1) AS net_change_pp
FROM
    regimen_counts AS rc
CROSS JOIN
    total_cohort AS tc
ORDER BY
    CASE rc.regimen_type
        WHEN 'Basal-Bolus' THEN 1
        WHEN 'Basal' THEN 2
        WHEN 'Bolus' THEN 3
        WHEN 'Sliding-Scale' THEN 4
    END;
