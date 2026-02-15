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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 42 AND 52
),
ami_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code LIKE '410%')
        OR (icd_version = 10 AND icd_code LIKE 'I21%')
),
stay_metrics AS (
    SELECT
        s.hadm_id,
        s.hospital_expire_flag,
        DATETIME_DIFF(s.dischtime, s.admittime, HOUR) / 24.0 AS hospital_los_days,
        CASE
            WHEN ami.hadm_id IS NOT NULL THEN 'AMI (42-52, Male)'
            ELSE 'Age-Matched Control (42-52, Male)'
        END AS cohort,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity_72h
    FROM
        first_icu_stays AS s
    LEFT JOIN
        ami_admissions AS ami ON s.hadm_id = ami.hadm_id
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON s.stay_id = pe.stay_id
        AND pe.starttime BETWEEN s.intime AND DATETIME_ADD(s.intime, INTERVAL 72 HOUR)
    WHERE
        s.rn = 1
    GROUP BY
        s.hadm_id,
        s.hospital_expire_flag,
        s.dischtime,
        s.admittime,
        ami.hadm_id
)
SELECT
    cohort,
    COUNT(DISTINCT hadm_id) AS num_stays,
    APPROX_QUANTILES(diagnostic_intensity_72h, 100)[OFFSET(90)] AS p90_diagnostic_intensity,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM
    stay_metrics
GROUP BY
    cohort
ORDER BY
    cohort DESC;
