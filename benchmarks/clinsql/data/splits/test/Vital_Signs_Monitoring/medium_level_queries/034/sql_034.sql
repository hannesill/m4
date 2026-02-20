WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        icu.stay_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 37 AND 47
), niv_stays AS (
    SELECT DISTINCT
        pc.stay_id
    FROM
        patient_cohort AS pc
    JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON pc.stay_id = ce.stay_id
    WHERE
        ce.itemid = 223849 AND ce.value IN ('CPAP', 'BiPAP')
), max_dbp_per_stay AS (
    SELECT
        ns.stay_id,
        MAX(ce.valuenum) AS max_dbp
    FROM
        niv_stays AS ns
    JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON ns.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (220051, 8368)
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 20 AND 200
    GROUP BY
        ns.stay_id
)
SELECT
    COUNT(stay_id) AS number_of_patient_stays,
    ROUND(APPROX_QUANTILES(max_dbp, 100)[OFFSET(25)], 2) AS p25_max_dbp,
    ROUND(APPROX_QUANTILES(max_dbp, 100)[OFFSET(50)], 2) AS median_max_dbp,
    ROUND(APPROX_QUANTILES(max_dbp, 100)[OFFSET(75)], 2) AS p75_max_dbp,
    ROUND(AVG(max_dbp), 2) AS avg_max_dbp
FROM
    max_dbp_per_stay;
