WITH first_icu AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        i.stay_id,
        p.gender,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission,
        i.intime,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS hospital_los_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        (
            SELECT
                hadm_id,
                stay_id,
                intime,
                ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY intime) AS rn
            FROM
                `physionet-data.mimiciv_3_1_icu.icustays`
        ) AS i
        ON a.hadm_id = i.hadm_id AND i.rn = 1
),
ards_cohort_ids AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code LIKE '51882%')
        OR (icd_version = 10 AND icd_code LIKE 'J80%')
),
icu_procs AS (
    SELECT
        f.stay_id,
        f.hadm_id,
        f.gender,
        f.age_at_admission,
        f.hospital_expire_flag,
        f.hospital_los_days,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity_24h
    FROM
        first_icu AS f
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON f.stay_id = pe.stay_id
        AND pe.starttime BETWEEN f.intime AND DATETIME_ADD(f.intime, INTERVAL 24 HOUR)
    GROUP BY
        f.stay_id,
        f.hadm_id,
        f.gender,
        f.age_at_admission,
        f.hospital_expire_flag,
        f.hospital_los_days
)
SELECT
    'Female, 84-94, ARDS' AS cohort,
    COUNT(stay_id) AS n_stays,
    APPROX_QUANTILES(diagnostic_intensity_24h, 100)[OFFSET(25)] AS p25_diag_intensity,
    APPROX_QUANTILES(diagnostic_intensity_24h, 100)[OFFSET(75)] AS p75_diag_intensity,
    APPROX_QUANTILES(diagnostic_intensity_24h, 100)[OFFSET(95)] AS p95_diag_intensity,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_pct
FROM
    icu_procs
WHERE
    hadm_id IN (SELECT hadm_id FROM ards_cohort_ids)
    AND gender = 'F'
    AND age_at_admission BETWEEN 84 AND 94

UNION ALL

SELECT
    'General ICU Population' AS cohort,
    COUNT(stay_id) AS n_stays,
    APPROX_QUANTILES(diagnostic_intensity_24h, 100)[OFFSET(25)] AS p25_diag_intensity,
    APPROX_QUANTILES(diagnostic_intensity_24h, 100)[OFFSET(75)] AS p75_diag_intensity,
    APPROX_QUANTILES(diagnostic_intensity_24h, 100)[OFFSET(95)] AS p95_diag_intensity,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_pct
FROM
    icu_procs;
