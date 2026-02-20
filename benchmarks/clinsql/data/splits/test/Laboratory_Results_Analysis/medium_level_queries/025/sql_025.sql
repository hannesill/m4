WITH patient_cohort AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 58 AND 68
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '410%') OR
            (d.icd_version = 10 AND d.icd_code LIKE 'I21%') OR
            (d.icd_version = 9 AND d.icd_code IN ('78650', '78659')) OR
            (d.icd_version = 10 AND d.icd_code IN ('R079', 'R0789'))
        )
),
first_troponin AS (
    SELECT
        pc.hadm_id,
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY pc.hadm_id ORDER BY le.charttime ASC) AS measurement_rank
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON pc.hadm_id = le.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
),
elevated_initial_troponin_cohort AS (
    SELECT
        hadm_id
    FROM
        first_troponin
    WHERE
        measurement_rank = 1
        AND valuenum > 0.01
)
SELECT
    'Female, 58-68, Chest Pain/AMI, Initial Trop T > 0.01 ng/mL' AS cohort_description,
    COUNT(DISTINCT eitc.hadm_id) AS number_of_patients,
    COUNT(le.valuenum) AS total_troponin_t_measurements,
    ROUND(AVG(le.valuenum), 4) AS mean_troponin_t,
    ROUND(STDDEV(le.valuenum), 4) AS stddev_troponin_t,
    MIN(le.valuenum) AS min_troponin_t,
    MAX(le.valuenum) AS max_troponin_t
FROM
    elevated_initial_troponin_cohort AS eitc
INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON eitc.hadm_id = le.hadm_id
WHERE
    le.itemid = 51003
    AND le.valuenum IS NOT NULL;
