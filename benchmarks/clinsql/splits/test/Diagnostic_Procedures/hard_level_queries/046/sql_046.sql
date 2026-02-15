WITH first_icu_stays AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        i.stay_id,
        p.gender,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.intime,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS i ON a.hadm_id = i.hadm_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
),
ards_diagnoses AS (
    SELECT
        hadm_id,
        MAX(
            CASE
                WHEN (icd_version = 9 AND icd_code = '51882')
                OR (icd_version = 10 AND icd_code = 'J80')
                    THEN 1
                ELSE 0
            END
        ) AS has_ards_dx
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
        hadm_id
),
procedure_counts AS (
    SELECT
        icu.stay_id,
        COUNT(DISTINCT pe.itemid) AS diagnostic_utilization
    FROM
        first_icu_stays AS icu
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe ON icu.stay_id = pe.stay_id
    WHERE
        icu.rn = 1
        AND pe.starttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
    GROUP BY
        icu.stay_id
),
combined_data AS (
    SELECT
        icu.stay_id,
        icu.hospital_expire_flag,
        DATETIME_DIFF(icu.dischtime, icu.admittime, HOUR) / 24.0 AS hospital_los_days,
        COALESCE(pc.diagnostic_utilization, 0) AS diagnostic_utilization,
        CASE
            WHEN
                ards.has_ards_dx = 1
                AND icu.gender = 'F'
                AND icu.age_at_admission BETWEEN 37 AND 47
                THEN 'ARDS (Female, 37-47)'
            ELSE 'General ICU'
        END AS cohort
    FROM
        first_icu_stays AS icu
    LEFT JOIN
        ards_diagnoses AS ards ON icu.hadm_id = ards.hadm_id
    LEFT JOIN
        procedure_counts AS pc ON icu.stay_id = pc.stay_id
    WHERE
        icu.rn = 1
)
SELECT
    cohort,
    COUNT(stay_id) AS number_of_stays,
    MIN(diagnostic_utilization) AS min_diagnostic_utilization,
    APPROX_QUANTILES(diagnostic_utilization, 100)[OFFSET(75)] AS diagnostic_utilization_p75,
    APPROX_QUANTILES(diagnostic_utilization, 100)[OFFSET(90)] AS diagnostic_utilization_p90,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM
    combined_data
GROUP BY
    cohort
ORDER BY
    cohort;
