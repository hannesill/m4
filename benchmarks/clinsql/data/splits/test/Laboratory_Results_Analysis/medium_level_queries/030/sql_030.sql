WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS admission_age
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
),
ami_admissions AS (
    SELECT DISTINCT
        pc.subject_id,
        pc.hadm_id,
        pc.admittime
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON pc.hadm_id = d.hadm_id
    WHERE
        pc.admission_age BETWEEN 64 AND 74
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '410%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
        )
),
first_ami_admission AS (
    SELECT
        subject_id,
        hadm_id
    FROM
    (
        SELECT
            subject_id,
            hadm_id,
            ROW_NUMBER() OVER(PARTITION BY subject_id ORDER BY admittime ASC) as rn
        FROM ami_admissions
    )
    WHERE rn = 1
),
index_troponin AS (
    SELECT
        fa.subject_id,
        le.valuenum
    FROM
        first_ami_admission AS fa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON fa.hadm_id = le.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
        AND le.valuenum >= 0
        AND le.charttime IS NOT NULL
    QUALIFY ROW_NUMBER() OVER(PARTITION BY fa.hadm_id ORDER BY le.charttime ASC) = 1
),
categorized_patients AS (
    SELECT
        subject_id,
        CASE
            WHEN valuenum <= 0.014 THEN 'Normal'
            WHEN valuenum > 0.014 AND valuenum <= 0.052 THEN 'Borderline'
            WHEN valuenum > 0.052 THEN 'Myocardial Injury'
            ELSE 'Uncategorized'
        END AS troponin_category
    FROM
        index_troponin
),
summary AS (
    SELECT
        troponin_category,
        COUNT(DISTINCT subject_id) AS patient_count,
        (SELECT COUNT(DISTINCT subject_id) FROM categorized_patients) AS total_patients_with_troponin
    FROM
        categorized_patients
    GROUP BY
        troponin_category
)
SELECT
    s.troponin_category,
    s.patient_count,
    s.total_patients_with_troponin,
    ROUND((s.patient_count * 100.0 / s.total_patients_with_troponin), 2) AS percent_of_patients
FROM
    summary AS s
ORDER BY
    CASE
        WHEN s.troponin_category = 'Normal' THEN 1
        WHEN s.troponin_category = 'Borderline' THEN 2
        WHEN s.troponin_category = 'Myocardial Injury' THEN 3
        ELSE 4
    END;
