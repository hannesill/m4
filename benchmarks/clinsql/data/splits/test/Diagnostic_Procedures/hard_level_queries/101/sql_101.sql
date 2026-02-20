WITH first_icu_stay AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        i.stay_id,
        a.admittime,
        a.dischtime,
        i.intime,
        i.outtime,
        a.hospital_expire_flag,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
),
cohorts AS (
    SELECT
        icu.hadm_id,
        icu.stay_id,
        icu.intime,
        icu.outtime,
        icu.hospital_expire_flag,
        CASE
            WHEN dx.hadm_id IS NOT NULL THEN 'COPD Exacerbation'
            ELSE 'Age-Matched ICU'
        END AS cohort_group
    FROM first_icu_stay AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON icu.subject_id = p.subject_id
    LEFT JOIN (
        SELECT DISTINCT hadm_id
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
            (icd_version = 9 AND icd_code LIKE '49121%')
            OR (icd_version = 10 AND icd_code LIKE 'J44.1%')
    ) AS dx
        ON icu.hadm_id = dx.hadm_id
    WHERE
        icu.rn = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM icu.admittime) - p.anchor_year) BETWEEN 88 AND 98
),
metrics_per_stay AS (
    SELECT
        c.cohort_group,
        c.stay_id,
        c.hospital_expire_flag,
        DATETIME_DIFF(c.outtime, c.intime, HOUR) / 24.0 AS icu_los_days,
        COUNT(DISTINCT pe.itemid) AS procedure_burden_first_72h
    FROM cohorts AS c
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY
        c.cohort_group,
        c.stay_id,
        c.hospital_expire_flag,
        c.intime,
        c.outtime
)
SELECT
    cohort_group,
    COUNT(stay_id) AS number_of_stays,
    APPROX_QUANTILES(procedure_burden_first_72h, 100)[OFFSET(75)] AS p75_procedure_burden_first_72h,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM metrics_per_stay
GROUP BY
    cohort_group
ORDER BY
    cohort_group DESC;
