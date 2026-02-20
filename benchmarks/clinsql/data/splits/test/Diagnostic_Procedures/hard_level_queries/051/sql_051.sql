WITH sepsis_hadm_ids AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (icd_code LIKE '9959%' OR icd_code LIKE '78552%'))
        OR (icd_version = 10 AND icd_code LIKE 'A41%')
),
first_icu_stays AS (
    SELECT
        p.subject_id,
        p.gender,
        p.anchor_age,
        p.anchor_year,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.stay_id,
        i.intime,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
),
icu_cohorts AS (
    SELECT
        s.stay_id,
        s.hadm_id,
        s.admittime,
        s.dischtime,
        s.intime,
        s.hospital_expire_flag,
        (s.anchor_age + EXTRACT(YEAR FROM s.admittime) - s.anchor_year) AS age_at_admission,
        s.gender,
        CASE
            WHEN s.hadm_id IN (SELECT hadm_id FROM sepsis_hadm_ids) THEN 1
            ELSE 0
        END AS is_sepsis
    FROM first_icu_stays AS s
    WHERE s.rn = 1
),
proc_counts AS (
    SELECT
        c.stay_id,
        COUNT(DISTINCT pe.itemid) AS diagnostic_utilization
    FROM icu_cohorts AS c
    INNER JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
    WHERE
        pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 24 HOUR)
    GROUP BY c.stay_id
),
final_data AS (
    SELECT
        c.hadm_id,
        c.hospital_expire_flag,
        c.admittime,
        c.dischtime,
        COALESCE(pc.diagnostic_utilization, 0) AS diagnostic_utilization,
        CASE
            WHEN c.is_sepsis = 1 AND c.gender = 'M' AND c.age_at_admission BETWEEN 90 AND 100
                THEN 'Sepsis, Male, Age 90-100'
            ELSE 'General ICU Population'
        END AS cohort
    FROM icu_cohorts AS c
    LEFT JOIN proc_counts AS pc
        ON c.stay_id = pc.stay_id
)
SELECT
    cohort,
    COUNT(DISTINCT hadm_id) AS num_admissions,
    STDDEV(diagnostic_utilization) AS stddev_diagnostic_utilization,
    APPROX_QUANTILES(diagnostic_utilization, 100)[OFFSET(75)] AS p75_diagnostic_utilization,
    APPROX_QUANTILES(diagnostic_utilization, 100)[OFFSET(95)] AS p95_diagnostic_utilization,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct,
    AVG(DATETIME_DIFF(dischtime, admittime, HOUR) / 24.0) AS avg_hospital_los_days
FROM final_data
GROUP BY cohort
ORDER BY cohort DESC
