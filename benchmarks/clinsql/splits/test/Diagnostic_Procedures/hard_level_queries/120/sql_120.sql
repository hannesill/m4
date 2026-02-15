WITH first_icu_stay AS (
    SELECT
        i.hadm_id,
        i.stay_id,
        i.intime
    FROM
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
    QUALIFY ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) = 1
),
cohort AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id,
        icu.stay_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        icu.intime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    INNER JOIN
        first_icu_stay AS icu
        ON a.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 74 AND 84
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '578%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'K92%')
        )
),
diagnostic_intensity AS (
    SELECT
        c.stay_id,
        c.admittime,
        c.dischtime,
        c.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS procedure_count
    FROM
        cohort AS c
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY
        c.stay_id, c.admittime, c.dischtime, c.hospital_expire_flag
),
stratified_cohort AS (
    SELECT
        d.procedure_count,
        d.admittime,
        d.dischtime,
        d.hospital_expire_flag,
        NTILE(4) OVER (ORDER BY d.procedure_count) AS diagnostic_quartile
    FROM
        diagnostic_intensity AS d
)
SELECT
    s.diagnostic_quartile,
    COUNT(*) AS num_patients,
    AVG(s.procedure_count) AS avg_procedure_count,
    AVG(DATETIME_DIFF(s.dischtime, s.admittime, HOUR) / 24.0) AS avg_hospital_los_days,
    AVG(CAST(s.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM
    stratified_cohort AS s
GROUP BY
    s.diagnostic_quartile
ORDER BY
    s.diagnostic_quartile;
