WITH first_icu AS (
    SELECT
        stay_id,
        hadm_id,
        subject_id,
        intime,
        ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY intime) AS rn
    FROM
        `physionet-data.mimiciv_3_1_icu.icustays`
),
ugib_admissions AS (
    SELECT DISTINCT
        hadm_id
    FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code LIKE '578%')
        OR (icd_version = 10 AND (
            icd_code LIKE 'K920%' OR icd_code LIKE 'K921%' OR icd_code LIKE 'K922%'
        ))
),
cohort_with_scores AS (
    SELECT
        i.stay_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        COUNT(DISTINCT pe.itemid) AS diagnostic_utilization
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN first_icu AS i
        ON a.hadm_id = i.hadm_id
    INNER JOIN ugib_admissions AS ugib
        ON a.hadm_id = ugib.hadm_id
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
        ON i.stay_id = pe.stay_id
        AND pe.starttime BETWEEN i.intime AND DATETIME_ADD(i.intime, INTERVAL 24 HOUR)
    WHERE
        i.rn = 1
        AND p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 48 AND 58
    GROUP BY
        i.stay_id, a.hadm_id, a.admittime, a.dischtime, a.hospital_expire_flag
),
quintiles AS (
    SELECT
        cws.*,
        NTILE(5) OVER (ORDER BY cws.diagnostic_utilization) AS quintile_stratum
    FROM
        cohort_with_scores AS cws
)
SELECT
    q.quintile_stratum,
    COUNT(q.stay_id) AS number_of_stays,
    AVG(q.diagnostic_utilization) AS avg_diagnostic_procedures,
    AVG(DATETIME_DIFF(q.dischtime, q.admittime, HOUR) / 24.0) AS avg_hospital_los_days,
    AVG(CAST(q.hospital_expire_flag AS FLOAT64)) * 100 AS in_hospital_mortality_percent
FROM
    quintiles AS q
GROUP BY
    q.quintile_stratum
ORDER BY
    q.quintile_stratum;
