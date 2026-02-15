WITH
cohort AS (
    SELECT DISTINCT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 64 AND 74
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code LIKE '250%'
                OR d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%'
                OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%'
            )
        )
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code IN ('4280', '4281', '42821', '42831', '42841')
                OR d.icd_code IN ('I5021', 'I5031', 'I5041', 'I50810', 'I50811', 'I50813', 'I50814', 'I509')
            )
        )
),
medication_events AS (
    SELECT
        c.hadm_id,
        CASE
            WHEN LOWER(rx.drug) LIKE '%metformin%' THEN 'Metformin'
            WHEN LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%glimepiride%' THEN 'Sulfonylureas'
            WHEN LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' OR LOWER(rx.drug) LIKE '%saxagliptin%' OR LOWER(rx.drug) LIKE '%alogliptin%' THEN 'DPP-4 Inhibitors'
            WHEN LOWER(rx.drug) LIKE '%canagliflozin%' OR LOWER(rx.drug) LIKE '%dapagliflozin%' OR LOWER(rx.drug) LIKE '%empagliflozin%' THEN 'SGLT2 Inhibitors'
            WHEN LOWER(rx.drug) LIKE '%liraglutide%' OR LOWER(rx.drug) LIKE '%semaglutide%' OR LOWER(rx.drug) LIKE '%exenatide%' OR LOWER(rx.drug) LIKE '%dulaglutide%' THEN 'GLP-1 Agonists'
            WHEN LOWER(rx.drug) LIKE '%pioglitazone%' OR LOWER(rx.drug) LIKE '%rosiglitazone%' THEN 'Thiazolidinediones'
            WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
            ELSE NULL
        END AS medication_class,
        (DATETIME_DIFF(rx.starttime, c.admittime, HOUR) <= 12) AS is_first_12h,
        (DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 48) AS is_final_48h
    FROM
        cohort AS c
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
        ON c.hadm_id = rx.hadm_id
    WHERE
        rx.starttime IS NOT NULL
        AND rx.starttime >= c.admittime AND rx.starttime <= c.dischtime
),
all_classes AS (
    SELECT 'Insulin' AS medication_class UNION ALL
    SELECT 'Metformin' UNION ALL
    SELECT 'Sulfonylureas' UNION ALL
    SELECT 'DPP-4 Inhibitors' UNION ALL
    SELECT 'SGLT2 Inhibitors' UNION ALL
    SELECT 'GLP-1 Agonists' UNION ALL
    SELECT 'Thiazolidinediones'
),
initiation_counts AS (
    SELECT
        medication_class,
        COUNT(DISTINCT CASE WHEN is_first_12h THEN hadm_id END) AS first_12h_initiations,
        COUNT(DISTINCT CASE WHEN is_final_48h THEN hadm_id END) AS final_48h_initiations
    FROM
        medication_events
    WHERE medication_class IS NOT NULL
    GROUP BY
        medication_class
),
total_cohort_admissions AS (
    SELECT COUNT(DISTINCT hadm_id) AS total_admissions FROM cohort
)
SELECT
    ac.medication_class,
    ROUND(
        COALESCE(ic.first_12h_initiations, 0) * 100.0 / tca.total_admissions,
        2
    ) AS initiation_rate_first_12h_pct,
    ROUND(
        COALESCE(ic.final_48h_initiations, 0) * 100.0 / tca.total_admissions,
        2
    ) AS initiation_rate_final_48h_pct
FROM
    all_classes AS ac
LEFT JOIN
    initiation_counts AS ic ON ac.medication_class = ic.medication_class
CROSS JOIN
    total_cohort_admissions AS tca
ORDER BY
    ac.medication_class;
