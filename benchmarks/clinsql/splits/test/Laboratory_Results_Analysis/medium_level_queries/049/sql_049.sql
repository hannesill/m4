WITH first_troponin_all_admissions AS (
    SELECT
        hadm_id,
        valuenum,
        ROW_NUMBER() OVER(PARTITION BY hadm_id ORDER BY charttime ASC) as rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.labevents`
    WHERE
        itemid = 51003
        AND valuenum IS NOT NULL
        AND valuenum > 0
),
troponin_uln AS (
    SELECT
        APPROX_QUANTILES(valuenum, 100)[OFFSET(99)] as uln_99
    FROM
        first_troponin_all_admissions
    WHERE
        rn = 1
),
target_population_initial_troponin AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        le.valuenum as initial_troponin_t,
        ROW_NUMBER() OVER(PARTITION BY a.hadm_id ORDER BY le.charttime ASC) as rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON a.hadm_id = le.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 49 AND 59
        AND le.itemid = 51003
        AND le.valuenum IS NOT NULL
),
elevated_troponin_cohort AS (
    SELECT
        t.subject_id,
        t.hadm_id,
        t.initial_troponin_t
    FROM
        target_population_initial_troponin AS t
    CROSS JOIN
        troponin_uln
    WHERE
        t.rn = 1
        AND t.initial_troponin_t > troponin_uln.uln_99
)
SELECT
    'Male patients aged 49-59 with initial Troponin T > 99th percentile ULN' AS cohort_description,
    (SELECT ROUND(uln_99, 3) FROM troponin_uln) AS troponin_t_99pct_uln,
    COUNT(DISTINCT subject_id) AS number_of_patients,
    COUNT(hadm_id) AS number_of_admissions,
    ROUND(MIN(initial_troponin_t), 3) AS min_value,
    ROUND(APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(25)], 3) AS p25_value,
    ROUND(APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(50)], 3) AS p50_median_value,
    ROUND(APPROX_QUANTILES(initial_troponin_t, 100)[OFFSET(75)], 3) AS p75_value,
    ROUND(MAX(initial_troponin_t), 3) AS max_value
FROM
    elevated_troponin_cohort;
