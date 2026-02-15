WITH first_icu_stays AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        i.stay_id,
        a.admittime,
        i.intime,
        i.outtime,
        a.hospital_expire_flag,
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
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 65 AND 75
),
pe_cohort AS (
    SELECT
        fs.stay_id,
        fs.intime,
        fs.outtime,
        fs.hospital_expire_flag
    FROM
        first_icu_stays AS fs
    WHERE
        fs.rn = 1
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
            WHERE
                dx.hadm_id = fs.hadm_id
                AND (
                    (dx.icd_version = 9 AND dx.icd_code LIKE '4151%')
                    OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I26%')
                )
        )
),
cohort_metrics AS (
    SELECT
        pc.stay_id,
        pc.hospital_expire_flag,
        DATETIME_DIFF(pc.outtime, pc.intime, HOUR) / 24.0 AS icu_los_days,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity_72hr
    FROM
        pe_cohort AS pc
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON pc.stay_id = pe.stay_id
        AND pe.starttime BETWEEN pc.intime AND DATETIME_ADD(pc.intime, INTERVAL 72 HOUR)
    GROUP BY
        pc.stay_id,
        pc.hospital_expire_flag,
        icu_los_days
),
cohort_quartiles AS (
    SELECT
        cm.stay_id,
        cm.diagnostic_intensity_72hr,
        cm.icu_los_days,
        cm.hospital_expire_flag,
        NTILE(4) OVER (ORDER BY cm.diagnostic_intensity_72hr) AS diagnostic_quartile
    FROM
        cohort_metrics AS cm
)
SELECT
    cq.diagnostic_quartile,
    COUNT(cq.stay_id) AS num_patients,
    AVG(cq.diagnostic_intensity_72hr) AS avg_diagnostic_intensity,
    AVG(cq.icu_los_days) AS avg_icu_los_days,
    AVG(CAST(cq.hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_percent
FROM
    cohort_quartiles AS cq
GROUP BY
    cq.diagnostic_quartile
ORDER BY
    cq.diagnostic_quartile;
