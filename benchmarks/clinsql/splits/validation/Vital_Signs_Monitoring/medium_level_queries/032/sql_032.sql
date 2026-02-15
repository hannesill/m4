WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 53 AND 63
),

imc_stepdown_stays AS (
    SELECT
        pc.subject_id,
        pc.hadm_id,
        ie.stay_id
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON pc.hadm_id = ie.hadm_id
    WHERE
        ie.first_careunit LIKE '%Stepdown%' OR ie.first_careunit LIKE '%Intermediate%'
),

ventilated_stays AS (
    SELECT DISTINCT
        iss.stay_id
    FROM
        imc_stepdown_stays AS iss
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON iss.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (223849, 220339, 224695, 224688)
),

nighttime_sbp_measurements AS (
    SELECT
        vs.stay_id,
        ce.valuenum AS sbp_value
    FROM
        ventilated_stays AS vs
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON vs.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (220050, 51)
        AND EXTRACT(HOUR FROM ce.charttime) < 6
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 40 AND 250
)

SELECT
    COUNT(DISTINCT stay_id) AS number_of_patient_stays,
    COUNT(sbp_value) AS number_of_sbp_measurements,
    ROUND(AVG(sbp_value), 2) AS avg_nighttime_sbp,
    ROUND(STDDEV(sbp_value), 2) AS stddev_nighttime_sbp,
    ROUND(MIN(sbp_value), 2) AS min_nighttime_sbp,
    ROUND(MAX(sbp_value), 2) AS max_nighttime_sbp,
    ROUND(APPROX_QUANTILES(sbp_value, 100)[OFFSET(25)], 2) AS p25_nighttime_sbp,
    ROUND(APPROX_QUANTILES(sbp_value, 100)[OFFSET(50)], 2) AS median_nighttime_sbp,
    ROUND(APPROX_QUANTILES(sbp_value, 100)[OFFSET(75)], 2) AS p75_nighttime_sbp
FROM
    nighttime_sbp_measurements;
