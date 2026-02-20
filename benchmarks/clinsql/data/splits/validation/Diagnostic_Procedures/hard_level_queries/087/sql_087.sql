WITH first_icu AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        i.stay_id,
        p.gender,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission,
        i.intime,
        a.hospital_expire_flag,
        DATETIME_DIFF(i.outtime, i.intime, HOUR) / 24.0 AS icu_los_days
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
    QUALIFY ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) = 1
),
ich_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (
            icd_code LIKE '430%'
            OR icd_code LIKE '431%'
            OR icd_code LIKE '432%'
        ))
        OR (icd_version = 10 AND (
            icd_code LIKE 'I60%'
            OR icd_code LIKE 'I61%'
            OR icd_code LIKE 'I62%'
        ))
),
proc_counts AS (
    SELECT
        icu.stay_id,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity
    FROM first_icu AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON icu.stay_id = pe.stay_id
    WHERE
        pe.starttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
    GROUP BY icu.stay_id
),
cohort_data AS (
    SELECT
        f.stay_id,
        f.icu_los_days,
        f.hospital_expire_flag,
        COALESCE(pc.diagnostic_intensity, 0) AS diagnostic_intensity,
        CASE
            WHEN
                f.gender = 'F'
                AND f.age_at_admission BETWEEN 56 AND 66
                AND f.hadm_id IN (SELECT hadm_id FROM ich_admissions)
                THEN 'ICH Cohort (Female, 56-66)'
            ELSE 'General ICU Population'
        END AS cohort_group
    FROM first_icu AS f
    LEFT JOIN proc_counts AS pc
        ON f.stay_id = pc.stay_id
)
SELECT
    cohort_group,
    COUNT(stay_id) AS num_icu_stays,
    APPROX_QUANTILES(diagnostic_intensity, 100)[OFFSET(95)] AS p95_diagnostic_intensity_first_72h,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_percent
FROM cohort_data
GROUP BY cohort_group
ORDER BY cohort_group DESC;
