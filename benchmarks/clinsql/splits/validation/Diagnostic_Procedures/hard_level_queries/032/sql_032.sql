WITH icu_stays_ranked AS (
    SELECT
        i.hadm_id,
        i.stay_id,
        i.intime,
        ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS i
),
sepsis_hadm_ids AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND (icd_code LIKE '9959%' OR icd_code LIKE '78552%'))
        OR (icd_version = 10 AND icd_code LIKE 'A41%')
),
cohort_base AS (
    SELECT
        a.hadm_id,
        i.stay_id,
        i.intime,
        a.dischtime,
        a.admittime,
        a.hospital_expire_flag,
        CASE
            WHEN s.hadm_id IS NOT NULL THEN 'Sepsis (Female, Age 66-76)'
            ELSE 'Age-Matched ICU (Female, Age 66-76)'
        END AS cohort
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN icu_stays_ranked AS i
        ON a.hadm_id = i.hadm_id
    LEFT JOIN sepsis_hadm_ids AS s
        ON a.hadm_id = s.hadm_id
    WHERE
        i.rn = 1
        AND p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 66 AND 76
),
diagnostic_intensity AS (
    SELECT
        cb.stay_id,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity_48h
    FROM cohort_base AS cb
    INNER JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON cb.stay_id = pe.stay_id
    WHERE
        pe.starttime BETWEEN cb.intime AND DATETIME_ADD(cb.intime, INTERVAL 48 HOUR)
    GROUP BY
        cb.stay_id
),
final_cohort AS (
    SELECT
        cb.cohort,
        cb.stay_id,
        COALESCE(di.diagnostic_intensity_48h, 0) AS diagnostic_intensity_48h,
        DATETIME_DIFF(cb.dischtime, cb.admittime, HOUR) / 24.0 AS hospital_los_days,
        cb.hospital_expire_flag
    FROM cohort_base AS cb
    LEFT JOIN diagnostic_intensity AS di
        ON cb.stay_id = di.stay_id
)
SELECT
    cohort,
    COUNT(stay_id) AS num_icu_stays,
    APPROX_QUANTILES(diagnostic_intensity_48h, 100)[OFFSET(90)] AS p90_diagnostic_intensity_first_48h,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_percent
FROM final_cohort
GROUP BY
    cohort
ORDER BY
    cohort DESC;
