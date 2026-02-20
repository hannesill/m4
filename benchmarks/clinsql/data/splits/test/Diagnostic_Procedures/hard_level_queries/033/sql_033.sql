WITH first_icu AS (
    SELECT
        i.hadm_id,
        i.stay_id,
        i.intime,
        i.outtime,
        ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) AS rn
    FROM
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
),
cohort AS (
    SELECT
        icu.stay_id,
        icu.intime,
        icu.outtime,
        a.hospital_expire_flag
    FROM
        first_icu AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON icu.hadm_id = a.hadm_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        icu.rn = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 37 AND 47
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE
                d.hadm_id = a.hadm_id
                AND (
                    (d.icd_version = 9 AND d.icd_code LIKE '486%')
                    OR (d.icd_version = 10 AND d.icd_code LIKE 'J18%')
                )
        )
),
proc_metrics AS (
    SELECT
        c.stay_id,
        c.hospital_expire_flag,
        DATETIME_DIFF(c.outtime, c.intime, HOUR) / 24.0 AS icu_los_days,
        COUNT(DISTINCT pe.itemid) AS procedure_count
    FROM
        cohort AS c
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 48 HOUR)
    GROUP BY
        c.stay_id, c.hospital_expire_flag, c.intime, c.outtime
),
quintiles AS (
    SELECT
        pm.icu_los_days,
        pm.hospital_expire_flag,
        pm.procedure_count,
        NTILE(5) OVER (ORDER BY pm.procedure_count) AS procedure_quintile
    FROM
        proc_metrics AS pm
)
SELECT
    q.procedure_quintile,
    COUNT(*) AS num_patients,
    AVG(q.procedure_count) AS avg_procedure_count,
    AVG(q.icu_los_days) AS avg_icu_los_days,
    AVG(CAST(q.hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_pct
FROM
    quintiles AS q
GROUP BY
    q.procedure_quintile
ORDER BY
    q.procedure_quintile;
