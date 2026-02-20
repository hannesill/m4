WITH first_icu_stays AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        i.stay_id,
        p.gender,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        i.intime,
        ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i
        ON a.hadm_id = i.hadm_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
),
ich_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432'))
        OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62'))
),
procedure_burden AS (
    SELECT
        fis.stay_id,
        COUNT(DISTINCT pe.itemid) AS procedure_count
    FROM first_icu_stays AS fis
    INNER JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON fis.stay_id = pe.stay_id
    WHERE fis.rn = 1
      AND pe.starttime BETWEEN fis.intime AND DATETIME_ADD(fis.intime, INTERVAL 72 HOUR)
    GROUP BY fis.stay_id
),
cohorts AS (
    SELECT
        fis.hadm_id,
        fis.hospital_expire_flag,
        DATETIME_DIFF(fis.dischtime, fis.admittime, HOUR) / 24.0 AS hospital_los_days,
        COALESCE(pb.procedure_count, 0) AS procedure_burden,
        CASE
            WHEN
                fis.gender = 'F'
                AND fis.age_at_admission BETWEEN 50 AND 60
                AND ich.hadm_id IS NOT NULL
                THEN 'Female, 50-60, ICH'
            ELSE 'General ICU'
        END AS cohort_group
    FROM first_icu_stays AS fis
    LEFT JOIN ich_admissions AS ich
        ON fis.hadm_id = ich.hadm_id
    LEFT JOIN procedure_burden AS pb
        ON fis.stay_id = pb.stay_id
    WHERE fis.rn = 1
)
SELECT
    cohort_group,
    COUNT(hadm_id) AS num_stays,
    AVG(hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_pct,
    MAX(procedure_burden) AS max_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(25)] AS p25_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(50)] AS p50_procedure_burden,
    APPROX_QUANTILES(procedure_burden, 100)[OFFSET(90)] AS p90_procedure_burden
FROM cohorts
GROUP BY cohort_group
ORDER BY cohort_group DESC;
