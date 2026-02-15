WITH first_icu_stays AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        i.stay_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.intime,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
),
cohort AS (
    SELECT
        fs.subject_id,
        fs.hadm_id,
        fs.stay_id,
        fs.admittime,
        fs.dischtime,
        fs.hospital_expire_flag,
        fs.intime
    FROM
        first_icu_stays AS fs
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON fs.subject_id = p.subject_id
    WHERE
        fs.rn = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM fs.admittime) - p.anchor_year) BETWEEN 77 AND 87
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = fs.hadm_id
            AND (
                (d.icd_version = 9 AND d.icd_code LIKE '493%2')
                OR (d.icd_version = 10 AND d.icd_code LIKE 'J45%1')
            )
        )
),
procedure_burden AS (
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
        stay_id,
        procedure_count,
        DATETIME_DIFF(dischtime, admittime, HOUR) / 24.0 AS hospital_los_days,
        hospital_expire_flag,
        NTILE(4) OVER (ORDER BY procedure_count) AS procedure_quartile
    FROM
        procedure_burden
)
SELECT
    procedure_quartile,
    COUNT(stay_id) AS num_patients,
    AVG(procedure_count) AS avg_procedure_count,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_percent
FROM
    stratified_cohort
GROUP BY
    procedure_quartile
ORDER BY
    procedure_quartile;
