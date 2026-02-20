WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
        AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
),
cohort_with_diagnoses AS (
    SELECT
        pc.hadm_id,
        pc.admittime,
        pc.dischtime
    FROM
        patient_cohort AS pc
    JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON pc.hadm_id = dx.hadm_id
    WHERE
        dx.icd_code LIKE '250%' OR dx.icd_code LIKE 'E08%' OR dx.icd_code LIKE 'E09%' OR dx.icd_code LIKE 'E10%' OR dx.icd_code LIKE 'E11%' OR dx.icd_code LIKE 'E13%'
    INTERSECT DISTINCT
    SELECT
        pc.hadm_id,
        pc.admittime,
        pc.dischtime
    FROM
        patient_cohort AS pc
    JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON pc.hadm_id = dx.hadm_id
    WHERE
        dx.icd_code LIKE '428%' OR dx.icd_code LIKE 'I50%'
),
medication_initiations AS (
    SELECT
        hadm_id,
        medication_class,
        starttime
    FROM (
        SELECT
            c.hadm_id,
            rx.starttime,
            CASE
                WHEN LOWER(rx.drug) LIKE '%insulin%' OR LOWER(rx.drug) LIKE '%metformin%' OR LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' THEN 'Antidiabetic'
                WHEN LOWER(rx.drug) LIKE '%metoprolol%' OR LOWER(rx.drug) LIKE '%carvedilol%' OR LOWER(rx.drug) LIKE '%bisoprolol%' OR LOWER(rx.drug) LIKE '%atenolol%' THEN 'Beta-Blocker'
                WHEN LOWER(rx.drug) LIKE '%lisinopril%' OR LOWER(rx.drug) LIKE '%enalapril%' OR LOWER(rx.drug) LIKE '%ramipril%' OR LOWER(rx.drug) LIKE '%losartan%' OR LOWER(rx.drug) LIKE '%valsartan%' OR LOWER(rx.drug) LIKE '%candesartan%' OR LOWER(rx.drug) LIKE '%sacubitril%' THEN 'ACEi/ARB/ARNI'
                WHEN LOWER(rx.drug) LIKE '%furosemide%' OR LOWER(rx.drug) LIKE '%bumetanide%' OR LOWER(rx.drug) LIKE '%torsemide%' THEN 'Loop Diuretic'
                ELSE NULL
            END AS medication_class,
            ROW_NUMBER() OVER(PARTITION BY c.hadm_id,
                CASE
                    WHEN LOWER(rx.drug) LIKE '%insulin%' OR LOWER(rx.drug) LIKE '%metformin%' OR LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' THEN 'Antidiabetic'
                    WHEN LOWER(rx.drug) LIKE '%metoprolol%' OR LOWER(rx.drug) LIKE '%carvedilol%' OR LOWER(rx.drug) LIKE '%bisoprolol%' OR LOWER(rx.drug) LIKE '%atenolol%' THEN 'Beta-Blocker'
                    WHEN LOWER(rx.drug) LIKE '%lisinopril%' OR LOWER(rx.drug) LIKE '%enalapril%' OR LOWER(rx.drug) LIKE '%ramipril%' OR LOWER(rx.drug) LIKE '%losartan%' OR LOWER(rx.drug) LIKE '%valsartan%' OR LOWER(rx.drug) LIKE '%candesartan%' OR LOWER(rx.drug) LIKE '%sacubitril%' THEN 'ACEi/ARB/ARNI'
                    WHEN LOWER(rx.drug) LIKE '%furosemide%' OR LOWER(rx.drug) LIKE '%bumetanide%' OR LOWER(rx.drug) LIKE '%torsemide%' THEN 'Loop Diuretic'
                    ELSE NULL
                END
            ORDER BY rx.starttime) as rn
        FROM
            cohort_with_diagnoses AS c
        JOIN
            `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON c.hadm_id = rx.hadm_id
        WHERE
            rx.starttime IS NOT NULL
            AND rx.starttime BETWEEN c.admittime AND c.dischtime
    )
    WHERE medication_class IS NOT NULL AND rn = 1
),
first_initiations_by_window AS (
    SELECT
        mi.hadm_id,
        mi.medication_class,
        CASE
            WHEN DATETIME_DIFF(mi.starttime, c.admittime, HOUR) <= 48 THEN 1
            ELSE 0
        END AS initiated_in_first_48h,
        CASE
            WHEN DATETIME_DIFF(c.dischtime, mi.starttime, HOUR) <= 12 THEN 1
            ELSE 0
        END AS initiated_in_last_12h
    FROM
        medication_initiations AS mi
    JOIN
        cohort_with_diagnoses AS c ON mi.hadm_id = c.hadm_id
)
SELECT
    med_windows.medication_class,
    total_admissions.n_admissions AS total_cohort_admissions,
    SUM(med_windows.initiated_in_first_48h) AS early_window_initiations,
    SUM(med_windows.initiated_in_last_12h) AS late_window_initiations,
    ROUND(SUM(med_windows.initiated_in_first_48h) * 100.0 / total_admissions.n_admissions, 2) AS early_initiation_rate_pct,
    ROUND(SUM(med_windows.initiated_in_last_12h) * 100.0 / total_admissions.n_admissions, 2) AS late_initiation_rate_pct,
    ROUND(
        (SUM(med_windows.initiated_in_last_12h) * 100.0 / total_admissions.n_admissions)
        - (SUM(med_windows.initiated_in_first_48h) * 100.0 / total_admissions.n_admissions),
    2) AS net_change_pp
FROM
    first_initiations_by_window AS med_windows
CROSS JOIN
    (SELECT COUNT(DISTINCT hadm_id) AS n_admissions FROM cohort_with_diagnoses) AS total_admissions
GROUP BY
    med_windows.medication_class,
    total_admissions.n_admissions
ORDER BY
    med_windows.medication_class;
