WITH patient_cohort AS (
    SELECT DISTINCT
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes ON a.hadm_id = d_diabetes.hadm_id
    JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf ON a.hadm_id = d_hf.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
        AND (d_diabetes.icd_code LIKE '250%' OR d_diabetes.icd_code LIKE 'E10%' OR d_diabetes.icd_code LIKE 'E11%')
        AND (d_hf.icd_code LIKE '428%' OR d_hf.icd_code LIKE 'I50%')
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 120
),
medication_events AS (
    SELECT
        pc.hadm_id,
        CASE
            WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
            ELSE 'Oral Agent'
        END AS medication_class,
        CASE
            WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 48 THEN 'First_48_Hours'
            WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 72 THEN 'Final_72_Hours'
            ELSE NULL
        END AS initiation_window
    FROM
        patient_cohort AS pc
    JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON pc.hadm_id = rx.hadm_id
    WHERE
        (
            LOWER(rx.drug) LIKE '%insulin%'
            OR LOWER(rx.drug) LIKE '%metformin%'
            OR LOWER(rx.drug) LIKE '%glipizide%'
            OR LOWER(rx.drug) LIKE '%glyburide%'
            OR LOWER(rx.drug) LIKE '%sitagliptin%'
            OR LOWER(rx.drug) LIKE '%linagliptin%'
        )
        AND rx.starttime IS NOT NULL
        AND rx.starttime BETWEEN pc.admittime AND pc.dischtime
),
aggregated_data AS (
    SELECT
        medication_class,
        COUNT(DISTINCT CASE WHEN initiation_window = 'First_48_Hours' THEN hadm_id END) AS early_initiations,
        COUNT(DISTINCT CASE WHEN initiation_window = 'Final_72_Hours' THEN hadm_id END) AS discharge_initiations
    FROM
        medication_events
    WHERE
        initiation_window IS NOT NULL
    GROUP BY
        medication_class
)
SELECT
    ad.medication_class,
    total.total_cohort_admissions,
    ad.early_initiations,
    ad.discharge_initiations,
    ROUND(ad.early_initiations * 100.0 / total.total_cohort_admissions, 2) AS early_initiation_rate_pct,
    ROUND(ad.discharge_initiations * 100.0 / total.total_cohort_admissions, 2) AS discharge_initiation_rate_pct,
    ROUND(
        (ad.discharge_initiations * 100.0 / total.total_cohort_admissions) - (ad.early_initiations * 100.0 / total.total_cohort_admissions),
        2
    ) AS net_change_pp
FROM
    aggregated_data AS ad
CROSS JOIN
    (SELECT COUNT(DISTINCT hadm_id) AS total_cohort_admissions FROM patient_cohort) AS total
ORDER BY
    ad.medication_class;
