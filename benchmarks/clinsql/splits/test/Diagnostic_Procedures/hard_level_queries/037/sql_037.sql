WITH first_icu_stays AS (
    SELECT
        p.gender,
        p.anchor_age,
        p.anchor_year,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.stay_id,
        i.intime,
        i.outtime,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
),
cohort_base AS (
    SELECT
        hadm_id,
        stay_id,
        intime,
        outtime,
        dischtime,
        admittime,
        hospital_expire_flag
    FROM
        first_icu_stays
    WHERE
        rn = 1
        AND gender = 'F'
        AND age_at_admission BETWEEN 53 AND 63
),
sepsis_admissions AS (
    SELECT DISTINCT
        hadm_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (icd_code LIKE '9959%' OR icd_code LIKE '78552%'))
        OR (icd_version = 10 AND icd_code LIKE 'A41%')
),
procedure_burden AS (
    SELECT
        pe.stay_id,
        COUNT(DISTINCT pe.itemid) AS num_procedures
    FROM
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
    INNER JOIN
        cohort_base AS cb
        ON pe.stay_id = cb.stay_id
    WHERE
        pe.starttime BETWEEN cb.intime AND DATETIME_ADD(cb.intime, INTERVAL 24 HOUR)
    GROUP BY
        pe.stay_id
),
final_cohort_data AS (
    SELECT
        cb.stay_id,
        CASE
            WHEN sa.hadm_id IS NOT NULL THEN 'Sepsis (Female, 53-63)'
            ELSE 'General ICU (Female, 53-63)'
        END AS cohort,
        COALESCE(pb.num_procedures, 0) AS procedure_burden_24hr,
        DATETIME_DIFF(cb.outtime, cb.intime, HOUR) / 24.0 AS icu_los_days,
        CAST(cb.hospital_expire_flag AS FLOAT64) AS hospital_mortality
    FROM
        cohort_base AS cb
    LEFT JOIN
        sepsis_admissions AS sa
        ON cb.hadm_id = sa.hadm_id
    LEFT JOIN
        procedure_burden AS pb
        ON cb.stay_id = pb.stay_id
)
SELECT
    cohort,
    COUNT(stay_id) AS number_of_stays,
    APPROX_QUANTILES(procedure_burden_24hr, 100)[OFFSET(75)] AS p75_procedure_burden,
    APPROX_QUANTILES(procedure_burden_24hr, 100)[OFFSET(90)] AS p90_procedure_burden,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(hospital_mortality) * 100 AS hospital_mortality_percent
FROM
    final_cohort_data
GROUP BY
    cohort
ORDER BY
    cohort DESC;
