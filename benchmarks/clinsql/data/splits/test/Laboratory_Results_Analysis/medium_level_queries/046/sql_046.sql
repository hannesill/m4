WITH patient_base AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND a.dischtime IS NOT NULL
        AND a.admittime IS NOT NULL
),
cohort_with_diagnosis AS (
    SELECT
        pb.subject_id,
        pb.hadm_id,
        pb.admittime,
        pb.dischtime,
        pb.age_at_admission
    FROM
        patient_base AS pb
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON pb.hadm_id = dx.hadm_id
    WHERE
        pb.age_at_admission BETWEEN 83 AND 93
        AND (
            dx.icd_code LIKE '410%' OR
            dx.icd_code LIKE 'I21%' OR
            dx.icd_code IN ('78650', '78651', '78659', 'R07.1', 'R07.2', 'R07.82', 'R07.89', 'R07.9')
        )
    GROUP BY
        pb.subject_id,
        pb.hadm_id,
        pb.admittime,
        pb.dischtime,
        pb.age_at_admission
),
first_troponin_t AS (
    SELECT
        le.hadm_id,
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
        cohort_with_diagnosis AS cwd
        ON le.hadm_id = cwd.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
        AND le.valuenum >= 0
),
final_cohort AS (
    SELECT
        cwd.subject_id,
        cwd.hadm_id,
        cwd.age_at_admission,
        cwd.admittime,
        cwd.dischtime,
        ft.valuenum AS first_troponin_t_value
    FROM
        cohort_with_diagnosis AS cwd
    INNER JOIN
        first_troponin_t AS ft
        ON cwd.hadm_id = ft.hadm_id
    WHERE
        ft.rn = 1
        AND ft.valuenum > 0.01
)
SELECT
    'Male Patients (83-93) with Chest Pain/AMI and Elevated Initial Troponin T' AS cohort_description,
    COUNT(DISTINCT subject_id) AS number_of_patients,
    ROUND(AVG(age_at_admission), 1) AS average_age,
    ROUND(AVG(DATETIME_DIFF(dischtime, admittime, DAY)), 1) AS avg_length_of_stay_days,
    ROUND(AVG(first_troponin_t_value), 2) AS avg_initial_troponin_t,
    ROUND(MIN(first_troponin_t_value), 2) AS min_initial_troponin_t,
    ROUND(MAX(first_troponin_t_value), 2) AS max_initial_troponin_t,
    ROUND(STDDEV(first_troponin_t_value), 2) AS stddev_initial_troponin_t,
    COUNTIF(first_troponin_t_value > 10) AS count_highly_elevated_trop_gt_10
FROM
    final_cohort;
