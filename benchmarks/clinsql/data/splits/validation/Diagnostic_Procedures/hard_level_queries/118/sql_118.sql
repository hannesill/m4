WITH cohort_admissions AS (
    SELECT DISTINCT
        a.hadm_id,
        a.subject_id
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 44 AND 54
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '410%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
        )
),
first_icu_stays AS (
    SELECT
        i.stay_id,
        i.hadm_id,
        i.intime,
        ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS i
    INNER JOIN cohort_admissions AS c
        ON i.hadm_id = c.hadm_id
),
procedure_counts AS (
    SELECT
        i.stay_id,
        i.hadm_id,
        COUNT(DISTINCT pe.itemid) AS procedure_count
    FROM first_icu_stays AS i
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON i.stay_id = pe.stay_id
        AND pe.starttime BETWEEN i.intime AND DATETIME_ADD(i.intime, INTERVAL 72 HOUR)
    WHERE i.rn = 1
    GROUP BY
        i.stay_id,
        i.hadm_id
),
quartiles AS (
    SELECT
        APPROX_QUANTILES(procedure_count, 100)[OFFSET(25)] AS p25,
        APPROX_QUANTILES(procedure_count, 100)[OFFSET(50)] AS p50,
        APPROX_QUANTILES(procedure_count, 100)[OFFSET(75)] AS p75
    FROM procedure_counts
),
stratified_stays AS (
    SELECT
        pc.hadm_id,
        pc.procedure_count,
        CASE
            WHEN pc.procedure_count <= q.p25 THEN 1
            WHEN pc.procedure_count > q.p25 AND pc.procedure_count <= q.p50 THEN 2
            WHEN pc.procedure_count > q.p50 AND pc.procedure_count <= q.p75 THEN 3
            ELSE 4
        END AS procedure_quartile
    FROM procedure_counts AS pc
    CROSS JOIN quartiles AS q
)
SELECT
    s.procedure_quartile,
    COUNT(DISTINCT s.hadm_id) AS num_patients,
    AVG(s.procedure_count) AS avg_procedure_count,
    AVG(DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0) AS avg_hospital_los_days,
    AVG(CAST(a.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_percent
FROM stratified_stays AS s
INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON s.hadm_id = a.hadm_id
GROUP BY
    s.procedure_quartile
ORDER BY
    s.procedure_quartile;
