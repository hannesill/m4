WITH cohort_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 44 AND 54
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
            WHERE dx.hadm_id = a.hadm_id
            AND (
                (dx.icd_version = 9 AND dx.icd_code LIKE '4151%')
                OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I26%')
            )
        )
),
first_icu_stays AS (
    SELECT
        ca.hadm_id,
        ca.subject_id,
        ca.admittime,
        ca.dischtime,
        ca.hospital_expire_flag,
        i.stay_id,
        i.intime
    FROM
        cohort_admissions AS ca
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON ca.hadm_id = i.hadm_id
    QUALIFY ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) = 1
),
diagnostic_intensity AS (
    SELECT
        fis.hadm_id,
        fis.admittime,
        fis.dischtime,
        fis.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS diagnostic_proc_count
    FROM
        first_icu_stays AS fis
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON fis.stay_id = pe.stay_id
        AND pe.starttime BETWEEN fis.intime AND DATETIME_ADD(fis.intime, INTERVAL 72 HOUR)
    GROUP BY
        fis.hadm_id,
        fis.admittime,
        fis.dischtime,
        fis.hospital_expire_flag
),
intensity_quintiles AS (
    SELECT
        di.hadm_id,
        di.admittime,
        di.dischtime,
        di.hospital_expire_flag,
        di.diagnostic_proc_count,
        NTILE(5) OVER (ORDER BY di.diagnostic_proc_count) AS diagnostic_intensity_quintile
    FROM
        diagnostic_intensity AS di
)
SELECT
    iq.diagnostic_intensity_quintile,
    COUNT(DISTINCT iq.hadm_id) AS num_patients,
    AVG(iq.diagnostic_proc_count) AS avg_diagnostic_procedures,
    AVG(DATETIME_DIFF(iq.dischtime, iq.admittime, HOUR) / 24.0) AS avg_hospital_los_days,
    AVG(CAST(iq.hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_percent
FROM
    intensity_quintiles AS iq
GROUP BY
    iq.diagnostic_intensity_quintile
ORDER BY
    iq.diagnostic_intensity_quintile;
