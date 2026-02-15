WITH first_icu AS (
    SELECT
        hadm_id,
        stay_id,
        intime,
        outtime,
        ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY intime) AS rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays`
),
pneumonia_cohort AS (
    SELECT DISTINCT
        p.subject_id,
        a.hadm_id,
        i.stay_id,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        i.intime,
        i.outtime,
        a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN first_icu AS i
        ON a.hadm_id = i.hadm_id AND i.rn = 1
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON a.hadm_id = dx.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 88 AND 98
        AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '486%')
            OR (dx.icd_version = 10 AND dx.icd_code LIKE 'J18%')
        )
),
stay_metrics AS (
    SELECT
        c.stay_id,
        c.hospital_expire_flag,
        DATETIME_DIFF(c.outtime, c.intime, HOUR) / 24.0 AS icu_los_days,
        COUNT(DISTINCT pe.itemid) AS diagnostic_utilization_score
    FROM pneumonia_cohort AS c
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY
        c.stay_id,
        c.hospital_expire_flag,
        c.intime,
        c.outtime
),
stratified_stays AS (
    SELECT
        stay_id,
        icu_los_days,
        hospital_expire_flag,
        diagnostic_utilization_score,
        NTILE(5) OVER (ORDER BY diagnostic_utilization_score) AS quintile_stratum
    FROM stay_metrics
)
SELECT
    s.quintile_stratum,
    COUNT(s.stay_id) AS num_icu_stays,
    AVG(s.diagnostic_utilization_score) AS avg_diagnostic_utilization,
    AVG(s.icu_los_days) AS avg_icu_los_days,
    AVG(CAST(s.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM stratified_stays AS s
GROUP BY
    s.quintile_stratum
ORDER BY
    s.quintile_stratum;
