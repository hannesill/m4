WITH aged_male_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND a.admittime IS NOT NULL
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 90 AND 100
),
chest_pain_admissions AS (
    SELECT DISTINCT
        amc.hadm_id,
        amc.subject_id
    FROM
        aged_male_cohort AS amc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON amc.hadm_id = dx.hadm_id
    WHERE
        dx.icd_code LIKE '786.5%'
        OR
        dx.icd_code LIKE 'R07%'
),
initial_troponin AS (
    SELECT
        cpa.hadm_id,
        cpa.subject_id,
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY cpa.hadm_id ORDER BY le.charttime ASC) AS measurement_rank
    FROM
        chest_pain_admissions AS cpa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON cpa.hadm_id = le.hadm_id
    WHERE
        le.itemid = 50911
        AND le.valuenum IS NOT NULL
),
elevated_initial_troponin AS (
    SELECT
        hadm_id,
        subject_id,
        valuenum
    FROM
        initial_troponin
    WHERE
        measurement_rank = 1
        AND valuenum > 0.04
)
SELECT
    COUNT(DISTINCT subject_id) AS patient_count,
    ROUND(MIN(valuenum), 3) AS min_troponin_i,
    ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(25)], 3) AS p25_troponin_i,
    ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(50)], 3) AS p50_troponin_i,
    ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)], 3) AS p75_troponin_i,
    ROUND(MAX(valuenum), 3) AS max_troponin_i
FROM
    elevated_initial_troponin;
