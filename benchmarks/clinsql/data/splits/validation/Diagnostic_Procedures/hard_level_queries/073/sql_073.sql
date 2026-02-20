WITH first_icu_stays AS (
    SELECT
        i.subject_id,
        i.hadm_id,
        i.stay_id,
        i.intime,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        p.gender,
        p.anchor_age,
        p.anchor_year,
        ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) as rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS i
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON i.hadm_id = a.hadm_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON i.subject_id = p.subject_id
),
cohort_base AS (
    SELECT
        s.subject_id,
        s.hadm_id,
        s.stay_id,
        s.intime,
        s.admittime,
        s.dischtime,
        s.hospital_expire_flag
    FROM first_icu_stays AS s
    WHERE
        s.rn = 1
        AND s.gender = 'M'
        AND (s.anchor_age + EXTRACT(YEAR FROM s.admittime) - s.anchor_year) BETWEEN 90 AND 100
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = s.hadm_id
            AND (
                (d.icd_version = 9 AND (
                    d.icd_code LIKE '570%' OR
                    d.icd_code LIKE '571%' OR
                    d.icd_code LIKE '572%' OR
                    d.icd_code LIKE '573%'
                )) OR
                (d.icd_version = 10 AND (
                    d.icd_code LIKE 'K70%' OR
                    d.icd_code LIKE 'K71%' OR
                    d.icd_code LIKE 'K72%' OR
                    d.icd_code LIKE 'K73%' OR
                    d.icd_code LIKE 'K74%' OR
                    d.icd_code LIKE 'K75%' OR
                    d.icd_code LIKE 'K76%'
                ))
            )
      )
),
diagnostic_intensity AS (
    SELECT
        cb.stay_id,
        cb.admittime,
        cb.dischtime,
        cb.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS diagnostic_intensity_count
    FROM cohort_base AS cb
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON cb.stay_id = pe.stay_id
        AND pe.starttime BETWEEN cb.intime AND DATETIME_ADD(cb.intime, INTERVAL 72 HOUR)
    GROUP BY
        cb.stay_id,
        cb.admittime,
        cb.dischtime,
        cb.hospital_expire_flag
),
quartile_boundaries AS (
    SELECT
        APPROX_QUANTILES(diagnostic_intensity_count, 4) AS quantiles
    FROM diagnostic_intensity
),
stratified_stays AS (
    SELECT
        di.diagnostic_intensity_count,
        DATETIME_DIFF(di.dischtime, di.admittime, HOUR) / 24.0 AS hospital_los_days,
        di.hospital_expire_flag,
        CASE
            WHEN di.diagnostic_intensity_count <= q.quantiles[OFFSET(1)] THEN 1
            WHEN di.diagnostic_intensity_count > q.quantiles[OFFSET(1)] AND di.diagnostic_intensity_count <= q.quantiles[OFFSET(2)] THEN 2
            WHEN di.diagnostic_intensity_count > q.quantiles[OFFSET(2)] AND di.diagnostic_intensity_count <= q.quantiles[OFFSET(3)] THEN 3
            ELSE 4
        END AS diagnostic_intensity_quartile
    FROM diagnostic_intensity AS di
    CROSS JOIN quartile_boundaries AS q
)
SELECT
    s.diagnostic_intensity_quartile,
    COUNT(*) AS num_patients,
    MIN(s.diagnostic_intensity_count) AS min_procedure_count,
    MAX(s.diagnostic_intensity_count) AS max_procedure_count,
    AVG(s.diagnostic_intensity_count) AS avg_procedure_count,
    AVG(s.hospital_los_days) AS avg_hospital_los_days,
    AVG(CAST(s.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_pct
FROM stratified_stays AS s
GROUP BY s.diagnostic_intensity_quartile
ORDER BY s.diagnostic_intensity_quartile;
