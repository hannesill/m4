WITH first_icu AS (
    SELECT
        stay_id,
        hadm_id,
        intime,
        outtime,
        ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY intime) AS rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays`
),
ami_cohort AS (
    SELECT
        a.hadm_id,
        i.stay_id,
        i.intime,
        i.outtime,
        a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN first_icu AS i
        ON a.hadm_id = i.hadm_id
    WHERE
        i.rn = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 76 AND 86
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
            WHERE
                dx.hadm_id = a.hadm_id
                AND (
                    (dx.icd_version = 9 AND dx.icd_code LIKE '410%')
                    OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I21%')
                )
        )
),
proc_counts AS (
    SELECT
        c.stay_id,
        c.intime,
        c.outtime,
        c.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity
    FROM ami_cohort AS c
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 24 HOUR)
    GROUP BY
        c.stay_id,
        c.intime,
        c.outtime,
        c.hospital_expire_flag
),
stratified_stays AS (
    SELECT
        pc.stay_id,
        pc.diagnostic_intensity,
        DATETIME_DIFF(pc.outtime, pc.intime, HOUR) / 24.0 AS icu_los_days,
        pc.hospital_expire_flag,
        NTILE(4) OVER (ORDER BY pc.diagnostic_intensity) AS diagnostic_quartile
    FROM proc_counts AS pc
)
SELECT
    s.diagnostic_quartile,
    COUNT(s.stay_id) AS num_stays,
    AVG(s.diagnostic_intensity) AS avg_diagnostic_intensity,
    AVG(s.icu_los_days) AS avg_icu_los_days,
    AVG(CAST(s.hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_pct
FROM stratified_stays AS s
GROUP BY
    s.diagnostic_quartile
ORDER BY
    s.diagnostic_quartile;
