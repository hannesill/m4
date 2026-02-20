WITH
target_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        ie.stay_id,
        ie.intime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 62 AND 72
        AND ie.intime IS NOT NULL AND ie.outtime IS NOT NULL
),
aki_diagnoses AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        icd_code IN ('5845', '5846', '5847', '5848', '5849') OR
        icd_code LIKE 'N17%'
),
temperature_measurements AS (
    SELECT
        tc.stay_id,
        tc.hadm_id,
        CASE
            WHEN ce.itemid IN (223761, 678) THEN (ce.valuenum - 32) * 5.0/9.0
            ELSE ce.valuenum
        END AS temperature_celsius
    FROM
        target_cohort AS tc
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON tc.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (
            223762,
            676,
            223761,
            678
        )
        AND ce.valuenum IS NOT NULL
        AND ce.charttime >= tc.intime AND ce.charttime <= DATETIME_ADD(tc.intime, INTERVAL 24 HOUR)
),
categorized_temps AS (
    SELECT
        tm.stay_id,
        tm.hadm_id,
        tm.temperature_celsius,
        CASE
            WHEN tm.temperature_celsius < 36.0 THEN 'Hypothermia (<36.0 C)'
            WHEN tm.temperature_celsius >= 36.0 AND tm.temperature_celsius < 38.0 THEN 'Normothermia (36.0-37.9 C)'
            WHEN tm.temperature_celsius >= 38.0 THEN 'Fever (>=38.0 C)'
            ELSE NULL
        END AS temperature_category,
        CASE WHEN aki.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS has_aki
    FROM
        temperature_measurements AS tm
    LEFT JOIN
        aki_diagnoses AS aki ON tm.hadm_id = aki.hadm_id
    WHERE
        tm.temperature_celsius BETWEEN 32 AND 43
),
temp_summary_stats AS (
    SELECT
        temperature_category,
        COUNT(DISTINCT stay_id) AS patient_count,
        COUNT(*) AS measurement_count,
        ROUND(AVG(temperature_celsius), 2) AS mean_temp_c,
        ROUND(APPROX_QUANTILES(temperature_celsius, 100)[OFFSET(50)], 2) AS median_temp_c,
        ROUND(
            APPROX_QUANTILES(temperature_celsius, 100)[OFFSET(75)] -
            APPROX_QUANTILES(temperature_celsius, 100)[OFFSET(25)], 2
        ) AS iqr_temp_c
    FROM
        categorized_temps
    WHERE
        temperature_category IS NOT NULL
    GROUP BY
        temperature_category
),
aki_rate_by_category AS (
    SELECT
        temperature_category,
        ROUND(
            100.0 * SUM(has_aki) / COUNT(DISTINCT stay_id), 1
        ) AS aki_rate_percent
    FROM (
        SELECT DISTINCT
            stay_id,
            temperature_category,
            has_aki
        FROM
            categorized_temps
        WHERE
            temperature_category IS NOT NULL
    ) AS patient_level_data
    GROUP BY
        temperature_category
)
SELECT
    tss.temperature_category,
    tss.patient_count,
    tss.measurement_count,
    tss.mean_temp_c,
    tss.median_temp_c,
    tss.iqr_temp_c,
    arc.aki_rate_percent
FROM
    temp_summary_stats AS tss
INNER JOIN
    aki_rate_by_category AS arc ON tss.temperature_category = arc.temperature_category
ORDER BY
    CASE
        WHEN tss.temperature_category = 'Hypothermia (<36.0 C)' THEN 1
        WHEN tss.temperature_category = 'Normothermia (36.0-37.9 C)' THEN 2
        WHEN tss.temperature_category = 'Fever (>=38.0 C)' THEN 3
    END;
