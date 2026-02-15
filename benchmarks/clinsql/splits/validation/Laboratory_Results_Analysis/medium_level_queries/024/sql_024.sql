WITH patient_cohort AS (
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 64 AND 74
        AND a.dischtime IS NOT NULL
),
chest_pain_admissions AS (
    SELECT DISTINCT
        pc.subject_id,
        pc.hadm_id,
        pc.admittime,
        pc.dischtime,
        pc.hospital_expire_flag,
        pc.age_at_admission
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON pc.hadm_id = dx.hadm_id
    WHERE
        (dx.icd_version = 9 AND STARTS_WITH(dx.icd_code, '7865'))
        OR
        (dx.icd_version = 10 AND STARTS_WITH(dx.icd_code, 'R07'))
),
initial_troponin_t AS (
    SELECT
        cpa.subject_id,
        cpa.hadm_id,
        cpa.admittime,
        cpa.dischtime,
        cpa.hospital_expire_flag,
        cpa.age_at_admission,
        le.valuenum AS initial_troponin_t_value,
        ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
    FROM
        chest_pain_admissions AS cpa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON cpa.hadm_id = le.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
        AND le.valuenum >= 0
),
final_cohort AS (
    SELECT
        subject_id,
        hadm_id,
        age_at_admission,
        hospital_expire_flag,
        initial_troponin_t_value,
        DATETIME_DIFF(dischtime, admittime, DAY) AS los_days
    FROM
        initial_troponin_t
    WHERE
        rn = 1
        AND initial_troponin_t_value > 0.014
),
summary_stats AS (
    SELECT
        COUNT(DISTINCT subject_id) AS total_patients,
        COUNT(hadm_id) AS total_admissions,
        AVG(age_at_admission) AS avg_age,
        AVG(los_days) AS avg_length_of_stay_days,
        AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_rate_percent,
        AVG(initial_troponin_t_value) AS avg_initial_troponin_t,
        STDDEV(initial_troponin_t_value) AS stddev_initial_troponin_t,
        MIN(initial_troponin_t_value) AS min_initial_troponin_t,
        MAX(initial_troponin_t_value) AS max_initial_troponin_t,
        APPROX_QUANTILES(initial_troponin_t_value, 4) AS troponin_quartiles
    FROM final_cohort
)
SELECT
    'Male Patients (64-74) with Chest Pain and Elevated Initial Troponin T' AS cohort_description,
    total_patients,
    total_admissions,
    ROUND(avg_age, 1) AS avg_age,
    ROUND(avg_length_of_stay_days, 1) AS avg_length_of_stay_days,
    ROUND(in_hospital_mortality_rate_percent, 2) AS in_hospital_mortality_rate_percent,
    ROUND(avg_initial_troponin_t, 3) AS avg_initial_troponin_t,
    ROUND(stddev_initial_troponin_t, 3) AS stddev_initial_troponin_t,
    ROUND(min_initial_troponin_t, 3) AS min_initial_troponin_t,
    ROUND(troponin_quartiles[OFFSET(1)], 3) AS p25_initial_troponin_t,
    ROUND(troponin_quartiles[OFFSET(2)], 3) AS median_initial_troponin_t,
    ROUND(troponin_quartiles[OFFSET(3)], 3) AS p75_initial_troponin_t,
    ROUND(max_initial_troponin_t, 3) AS max_initial_troponin_t
FROM
    summary_stats;
