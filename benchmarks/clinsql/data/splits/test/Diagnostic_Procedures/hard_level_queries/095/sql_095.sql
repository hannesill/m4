WITH first_icu_stays AS (
    SELECT
        p.subject_id,
        p.gender,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.stay_id,
        i.intime,
        i.outtime,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
),
pe_cohort_hadm_ids AS (
    SELECT DISTINCT fs.hadm_id
    FROM first_icu_stays AS fs
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON fs.hadm_id = dx.hadm_id
    WHERE
        fs.rn = 1
        AND fs.gender = 'M'
        AND fs.age_at_admission BETWEEN 79 AND 89
        AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '4151%')
            OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I26%')
        )
),
icu_stay_metrics AS (
    SELECT
        icu.stay_id,
        icu.hadm_id,
        icu.intime,
        icu.outtime,
        icu.hospital_expire_flag,
        COUNT(DISTINCT
            CASE
                WHEN pe.starttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 24 HOUR)
                    THEN pe.itemid
                ELSE NULL
            END
        ) AS diagnostic_utilization_score
    FROM first_icu_stays AS icu
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON icu.stay_id = pe.stay_id
    WHERE icu.rn = 1
    GROUP BY
        icu.stay_id,
        icu.hadm_id,
        icu.intime,
        icu.outtime,
        icu.hospital_expire_flag
)
SELECT
    'PE, Male, Age 79-89' AS cohort,
    COUNT(metrics.stay_id) AS num_icu_stays,
    APPROX_QUANTILES(metrics.diagnostic_utilization_score, 100)[OFFSET(75)] AS p75_diagnostic_utilization,
    AVG(DATETIME_DIFF(metrics.outtime, metrics.intime, HOUR) / 24.0) AS avg_icu_los_days,
    AVG(CAST(metrics.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_percent
FROM icu_stay_metrics AS metrics
WHERE metrics.hadm_id IN (SELECT hadm_id FROM pe_cohort_hadm_ids)
UNION ALL
SELECT
    'General ICU' AS cohort,
    COUNT(metrics.stay_id) AS num_icu_stays,
    NULL AS p75_diagnostic_utilization,
    AVG(DATETIME_DIFF(metrics.outtime, metrics.intime, HOUR) / 24.0) AS avg_icu_los_days,
    AVG(CAST(metrics.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_percent
FROM icu_stay_metrics AS metrics;
