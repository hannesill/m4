WITH first_icu_stays AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        i.stay_id,
        i.intime,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 82 AND 92
),
shock_cohort AS (
    SELECT DISTINCT
        s.subject_id,
        s.hadm_id,
        s.stay_id,
        s.intime,
        s.admittime,
        s.dischtime,
        s.hospital_expire_flag
    FROM
        first_icu_stays AS s
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON s.hadm_id = dx.hadm_id
    WHERE
        s.rn = 1
        AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '78551%')
            OR (dx.icd_version = 10 AND dx.icd_code LIKE 'R570%')
        )
),
procedure_burden AS (
    SELECT
        sc.stay_id,
        sc.hadm_id,
        sc.admittime,
        sc.dischtime,
        sc.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS procedure_count
    FROM
        shock_cohort AS sc
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON sc.stay_id = pe.stay_id
        AND pe.starttime BETWEEN sc.intime AND DATETIME_ADD(sc.intime, INTERVAL 24 HOUR)
    GROUP BY
        sc.stay_id,
        sc.hadm_id,
        sc.admittime,
        sc.dischtime,
        sc.hospital_expire_flag
),
quintiles AS (
    SELECT
        procedure_count,
        hospital_expire_flag,
        DATETIME_DIFF(dischtime, admittime, HOUR) / 24.0 AS hospital_los_days,
        NTILE(5) OVER (ORDER BY procedure_count) AS procedure_quintile
    FROM
        procedure_burden
)
SELECT
    procedure_quintile,
    COUNT(*) AS num_patients,
    AVG(procedure_count) AS avg_procedure_count,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_percent
FROM
    quintiles
GROUP BY
    procedure_quintile
ORDER BY
    procedure_quintile;
