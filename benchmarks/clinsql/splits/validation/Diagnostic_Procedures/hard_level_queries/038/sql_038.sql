WITH first_icu_stays AS (
    SELECT
        stay_id,
        hadm_id,
        intime,
        outtime,
        ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY intime) AS rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays`
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
icu_procedure_burden AS (
    SELECT
        icu.stay_id,
        COUNT(DISTINCT pe.itemid) AS procedure_burden_72h
    FROM first_icu_stays AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON icu.stay_id = pe.stay_id
    WHERE
        icu.rn = 1
        AND pe.starttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
    GROUP BY icu.stay_id
),
cohorts AS (
    SELECT
        icu.stay_id,
        CASE
            WHEN
                ich.hadm_id IS NOT NULL
                AND p.gender = 'M'
                AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 60 AND 70
            THEN 'ICH 60-70 Male'
            ELSE 'General ICU'
        END AS cohort,
        COALESCE(pb.procedure_burden_72h, 0) AS procedure_burden,
        DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days,
        a.hospital_expire_flag
    FROM first_icu_stays AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON icu.hadm_id = a.hadm_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    LEFT JOIN ich_admissions AS ich
        ON icu.hadm_id = ich.hadm_id
    LEFT JOIN icu_procedure_burden AS pb
        ON icu.stay_id = pb.stay_id
    WHERE
        icu.rn = 1
)
SELECT
    cohort,
    COUNT(stay_id) AS num_icu_stays,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(75)] AS p75_procedure_burden_first_72h,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM cohorts
GROUP BY cohort
ORDER BY cohort;
