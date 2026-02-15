WITH sepsis_hadms AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (icd_code LIKE '9959%' OR icd_code LIKE '78552%'))
        OR (icd_version = 10 AND icd_code LIKE 'A41%')
),
first_icu_stays AS (
    SELECT
        stay_id,
        hadm_id,
        ROW_NUMBER() OVER(PARTITION BY hadm_id ORDER BY intime ASC) as rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays`
),
cohort AS (
    SELECT
        i.stay_id,
        i.intime,
        a.hospital_expire_flag,
        DATETIME_DIFF(i.outtime, i.intime, HOUR) / 24.0 AS icu_los_days
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
    INNER JOIN first_icu_stays AS fis
        ON i.stay_id = fis.stay_id
    WHERE
        fis.rn = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 83 AND 93
        AND a.hadm_id IN (SELECT hadm_id FROM sepsis_hadms)
),
diagnostic_intensity AS (
    SELECT
        c.stay_id,
        c.icu_los_days,
        c.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS diagnostic_proc_count
    FROM cohort AS c
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY
        c.stay_id, c.icu_los_days, c.hospital_expire_flag
),
quartiles AS (
    SELECT
        APPROX_QUANTILES(diagnostic_proc_count, 4) AS quantiles
    FROM diagnostic_intensity
),
stratified_stays AS (
    SELECT
        di.diagnostic_proc_count,
        di.icu_los_days,
        di.hospital_expire_flag,
        CASE
            WHEN di.diagnostic_proc_count <= q.quantiles[OFFSET(1)] THEN 'Q1 (Lowest)'
            WHEN di.diagnostic_proc_count > q.quantiles[OFFSET(1)] AND di.diagnostic_proc_count <= q.quantiles[OFFSET(2)] THEN 'Q2'
            WHEN di.diagnostic_proc_count > q.quantiles[OFFSET(2)] AND di.diagnostic_proc_count <= q.quantiles[OFFSET(3)] THEN 'Q3'
            WHEN di.diagnostic_proc_count > q.quantiles[OFFSET(3)] THEN 'Q4 (Highest)'
            ELSE 'Unknown'
        END AS diagnostic_quartile
    FROM diagnostic_intensity AS di
    CROSS JOIN quartiles AS q
)
SELECT
    diagnostic_quartile,
    COUNT(diagnostic_quartile) AS num_icu_stays,
    AVG(diagnostic_proc_count) AS avg_diagnostic_procs,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent
FROM stratified_stays
GROUP BY
    diagnostic_quartile
ORDER BY
    diagnostic_quartile;
