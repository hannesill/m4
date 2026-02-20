WITH patient_base AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 58 AND 68
),

diagnosis_cohort AS (
    SELECT
        pb.subject_id,
        pb.hadm_id,
        pb.admittime,
        pb.dischtime,
        pb.hospital_expire_flag,
        pb.age_at_admission
    FROM
        patient_base AS pb
    WHERE EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE d.hadm_id = pb.hadm_id
        AND (
            (d.icd_version = 9 AND (
                d.icd_code LIKE '410%'
                OR d.icd_code IN ('78650', '78651', '78659')
            ))
            OR
            (d.icd_version = 10 AND (
                d.icd_code LIKE 'I21%'
                OR d.icd_code LIKE 'I22%'
                OR d.icd_code IN ('R071', 'R072', 'R0782', 'R0789', 'R079')
            ))
        )
    )
),

initial_troponin AS (
    SELECT
        dc.subject_id,
        dc.hadm_id,
        dc.admittime,
        dc.dischtime,
        dc.hospital_expire_flag,
        dc.age_at_admission,
        le.valuenum AS initial_troponin_t_value,
        ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
    FROM
        diagnosis_cohort AS dc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON dc.hadm_id = le.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
        AND le.valuenum >= 0
),

final_cohort AS (
    SELECT
        it.subject_id,
        it.hadm_id,
        it.age_at_admission,
        it.initial_troponin_t_value,
        it.hospital_expire_flag,
        DATETIME_DIFF(it.dischtime, it.admittime, DAY) AS length_of_stay_days
    FROM
        initial_troponin AS it
    WHERE
        it.rn = 1
        AND it.initial_troponin_t_value > 0.04
)

SELECT
    'Male Patients (58-68) with Chest Pain/AMI and Elevated Initial Troponin T' AS cohort_description,
    COUNT(DISTINCT subject_id) AS total_patients,
    COUNT(hadm_id) AS total_admissions,
    ROUND(AVG(age_at_admission), 1) AS avg_age,
    ROUND(AVG(length_of_stay_days), 1) AS avg_length_of_stay_days,
    ROUND(AVG(initial_troponin_t_value), 3) AS avg_initial_troponin_t,
    ROUND(MIN(initial_troponin_t_value), 3) AS min_initial_troponin_t,
    ROUND(MAX(initial_troponin_t_value), 3) AS max_initial_troponin_t,
    ROUND(APPROX_QUANTILES(initial_troponin_t_value, 100)[OFFSET(25)], 3) AS p25_initial_troponin_t,
    ROUND(APPROX_QUANTILES(initial_troponin_t_value, 100)[OFFSET(50)], 3) AS p50_initial_troponin_t,
    ROUND(APPROX_QUANTILES(initial_troponin_t_value, 100)[OFFSET(75)], 3) AS p75_initial_troponin_t,
    SUM(hospital_expire_flag) AS total_in_hospital_deaths,
    ROUND(
        (SUM(hospital_expire_flag) * 100.0) / COUNT(hadm_id),
        2
    ) AS in_hospital_mortality_rate_percent
FROM
    final_cohort
WHERE
    length_of_stay_days IS NOT NULL;
