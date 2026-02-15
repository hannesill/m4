WITH
base_stays AS (
    SELECT
        p.subject_id,
        p.gender,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.stay_id,
        i.intime,
        i.outtime,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
    QUALIFY ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) = 1
),
ich_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (
            icd_code LIKE '430%'
            OR icd_code LIKE '431%'
            OR icd_code LIKE '432%'
        ))
        OR (icd_version = 10 AND (
            icd_code LIKE 'I60%'
            OR icd_code LIKE 'I61%'
            OR icd_code LIKE 'I62%'
        ))
),
procedure_counts AS (
    SELECT
        pe.stay_id,
        COUNT(DISTINCT pe.itemid) AS procedure_burden
    FROM
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
    INNER JOIN
        base_stays AS bs ON pe.stay_id = bs.stay_id
    WHERE
        pe.starttime BETWEEN bs.intime AND DATETIME_ADD(bs.intime, INTERVAL 72 HOUR)
    GROUP BY
        pe.stay_id
),
cohort_data AS (
    SELECT
        bs.stay_id,
        bs.hospital_expire_flag,
        (
            bs.gender = 'F'
            AND bs.age_at_admission BETWEEN 50 AND 60
            AND ich.hadm_id IS NOT NULL
        ) AS is_target_cohort,
        COALESCE(pc.procedure_burden, 0) AS procedure_burden,
        DATETIME_DIFF(bs.outtime, bs.intime, HOUR) / 24.0 AS icu_los_days
    FROM
        base_stays AS bs
    LEFT JOIN
        ich_admissions AS ich ON bs.hadm_id = ich.hadm_id
    LEFT JOIN
        procedure_counts AS pc ON bs.stay_id = pc.stay_id
)
SELECT
    'Intracranial Hemorrhage (Female, 50-60)' AS cohort,
    COUNT(stay_id) AS number_of_stays,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(25)] AS p25_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(50)] AS p50_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(90)] AS p90_procedure_burden,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM
    cohort_data
WHERE
    is_target_cohort
UNION ALL
SELECT
    'General ICU' AS cohort,
    COUNT(stay_id) AS number_of_stays,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(25)] AS p25_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(50)] AS p50_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(90)] AS p90_procedure_burden,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM
    cohort_data;
