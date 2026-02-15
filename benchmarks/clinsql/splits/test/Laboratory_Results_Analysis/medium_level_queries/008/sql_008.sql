WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.hospital_expire_flag
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 87 AND 97
),
acs_admissions AS (
    SELECT DISTINCT
        pc.subject_id,
        pc.hadm_id,
        pc.hospital_expire_flag
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON pc.hadm_id = dx.hadm_id
    WHERE
        (dx.icd_version = 9 AND (
            dx.icd_code LIKE '410%'
            OR dx.icd_code = '4111'
        ))
        OR
        (dx.icd_version = 10 AND (
            STARTS_WITH(dx.icd_code, 'I21')
            OR STARTS_WITH(dx.icd_code, 'I22')
            OR dx.icd_code = 'I200'
        ))
),
first_troponin AS (
    SELECT
        acs.hadm_id,
        acs.hospital_expire_flag,
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
    FROM
        acs_admissions AS acs
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON acs.hadm_id = le.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
        AND le.valuenum >= 0
),
categorized_troponin AS (
    SELECT
        hadm_id,
        hospital_expire_flag,
        CASE
            WHEN valuenum <= 0.04 THEN 'Normal/Minimal'
            WHEN valuenum > 0.04 AND valuenum <= 0.10 THEN 'Borderline'
            WHEN valuenum > 0.10 THEN 'Elevated'
            ELSE 'Unknown'
        END AS troponin_category
    FROM
        first_troponin
    WHERE
        rn = 1
)
SELECT
    troponin_category,
    COUNT(hadm_id) AS admission_count,
    ROUND(100.0 * COUNT(hadm_id) / SUM(COUNT(hadm_id)) OVER(), 2) AS percentage_of_admissions,
    SUM(hospital_expire_flag) AS in_hospital_deaths,
    ROUND(100.0 * AVG(hospital_expire_flag), 2) AS in_hospital_mortality_rate_pct
FROM
    categorized_troponin
GROUP BY
    troponin_category
ORDER BY
    CASE
        WHEN troponin_category = 'Normal/Minimal' THEN 1
        WHEN troponin_category = 'Borderline' THEN 2
        WHEN troponin_category = 'Elevated' THEN 3
        ELSE 4
    END;
