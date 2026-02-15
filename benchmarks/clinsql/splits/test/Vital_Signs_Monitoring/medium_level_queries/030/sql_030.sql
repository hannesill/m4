WITH mi_admissions AS (
    SELECT DISTINCT
        hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code LIKE '410%')
        OR (icd_version = 10 AND (icd_code LIKE 'I21%' OR icd_code LIKE 'I22%'))
),
patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        ie.stay_id,
        ie.intime,
        CASE WHEN mi.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS has_mi
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON a.hadm_id = ie.hadm_id
    LEFT JOIN mi_admissions AS mi
        ON a.hadm_id = mi.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 81 AND 91
        AND ie.intime IS NOT NULL
),
first_24hr_temps AS (
    SELECT
        pc.stay_id,
        ce.valuenum AS temp_celsius
    FROM patient_cohort AS pc
    INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        ON pc.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (223762, 676)
        AND ce.valuenum IS NOT NULL
        AND ce.charttime BETWEEN pc.intime AND DATETIME_ADD(pc.intime, INTERVAL 24 HOUR)
        AND ce.valuenum BETWEEN 34 AND 43
),
avg_temp_per_stay AS (
    SELECT
        stay_id,
        AVG(temp_celsius) AS avg_temp
    FROM first_24hr_temps
    GROUP BY stay_id
),
categorized_stays AS (
    SELECT
        pc.stay_id,
        pc.has_mi,
        atps.avg_temp,
        CASE
            WHEN atps.avg_temp < 36.0 THEN 'Hypothermic (<36.0 C)'
            WHEN atps.avg_temp >= 36.0 AND atps.avg_temp < 38.0 THEN 'Normothermic (36.0-37.9 C)'
            WHEN atps.avg_temp >= 38.0 THEN 'Febrile (>=38.0 C)'
            ELSE NULL
        END AS temperature_category
    FROM avg_temp_per_stay AS atps
    INNER JOIN patient_cohort AS pc
        ON atps.stay_id = pc.stay_id
)
SELECT
    cs.temperature_category,
    COUNT(cs.stay_id) AS number_of_icu_stays,
    ROUND(AVG(cs.avg_temp), 2) AS mean_avg_temp,
    ROUND(APPROX_QUANTILES(cs.avg_temp, 100)[OFFSET(50)], 2) AS median_avg_temp,
    ROUND(
        (APPROX_QUANTILES(cs.avg_temp, 100)[OFFSET(75)] - APPROX_QUANTILES(cs.avg_temp, 100)[OFFSET(25)]),
        2
    ) AS iqr_avg_temp,
    SUM(cs.has_mi) AS mi_stays_count,
    ROUND(100.0 * AVG(cs.has_mi), 2) AS mi_rate_percent
FROM categorized_stays AS cs
WHERE cs.temperature_category IS NOT NULL
GROUP BY cs.temperature_category
ORDER BY
    CASE
        WHEN cs.temperature_category = 'Hypothermic (<36.0 C)' THEN 1
        WHEN cs.temperature_category = 'Normothermic (36.0-37.9 C)' THEN 2
        WHEN cs.temperature_category = 'Febrile (>=38.0 C)' THEN 3
    END;
