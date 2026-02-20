WITH first_icu AS (
    SELECT
        i.stay_id,
        i.hadm_id,
        i.subject_id,
        i.intime,
        i.outtime,
        a.admittime,
        a.hospital_expire_flag,
        p.gender,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_icu.icustays` AS i
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON i.hadm_id = a.hadm_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON i.subject_id = p.subject_id
    QUALIFY ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) = 1
),
hemorrhagic_stroke_hadm AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (icd_code LIKE '430%' OR icd_code LIKE '431%' OR icd_code LIKE '432%'))
        OR (icd_version = 10 AND (icd_code LIKE 'I60%' OR icd_code LIKE 'I61%' OR icd_code LIKE 'I62%'))
),
cohorts AS (
    SELECT
        fi.stay_id,
        fi.intime,
        fi.outtime,
        fi.hospital_expire_flag,
        CASE
            WHEN fi.hadm_id IN (SELECT hadm_id FROM hemorrhagic_stroke_hadm)
                THEN 'Hemorrhagic Stroke (Male, 40-50)'
            ELSE 'Age-Matched ICU (Male, 40-50)'
        END AS cohort_group
    FROM
        first_icu AS fi
    WHERE
        fi.gender = 'M'
        AND fi.age_at_admission BETWEEN 40 AND 50
),
metrics_per_stay AS (
    SELECT
        c.cohort_group,
        c.stay_id,
        c.hospital_expire_flag,
        DATETIME_DIFF(c.outtime, c.intime, HOUR) / 24.0 AS icu_los_days,
        COUNT(DISTINCT pe.itemid) AS diagnostic_load
    FROM
        cohorts AS c
    LEFT JOIN
        `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON c.stay_id = pe.stay_id
        AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY
        c.cohort_group, c.stay_id, c.hospital_expire_flag, c.intime, c.outtime
)
SELECT
    cohort_group,
    COUNT(stay_id) AS number_of_stays,
    APPROX_QUANTILES(diagnostic_load, 100)[OFFSET(90)] AS p90_diagnostic_load_first_72h,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM
    metrics_per_stay
GROUP BY
    cohort_group
ORDER BY
    cohort_group;
