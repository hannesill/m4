WITH
patients_with_age AS (
    SELECT
        p.subject_id,
        p.gender,
        a.hadm_id,
        a.admittime,
        (DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
),
hhs_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code LIKE '2502%')
        OR
        (icd_version = 10 AND (STARTS_WITH(icd_code, 'E110') OR STARTS_WITH(icd_code, 'E130')))
),
cohort_definition AS (
    SELECT
        icu.stay_id,
        icu.subject_id,
        icu.hadm_id,
        icu.intime,
        icu.outtime,
        pwa.age_at_admission,
        adm.hospital_expire_flag,
        CASE
            WHEN hhs.hadm_id IS NOT NULL THEN 'HHS_Target'
            ELSE 'Age_Matched_Control'
        END AS cohort_group
    FROM
        `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN
        patients_with_age AS pwa ON icu.hadm_id = pwa.hadm_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
    LEFT JOIN
        hhs_admissions AS hhs ON icu.hadm_id = hhs.hadm_id
    WHERE
        pwa.gender = 'M'
        AND pwa.age_at_admission BETWEEN 78 AND 88
),
vitals_first_48h AS (
    SELECT
        c.stay_id,
        CASE
            WHEN c.itemid = 220045 THEN 'HeartRate'
            WHEN c.itemid IN (220179, 220050) THEN 'SBP'
            WHEN c.itemid IN (220052, 225312) THEN 'MAP'
            WHEN c.itemid IN (220210, 224690) THEN 'RespRate'
            WHEN c.itemid = 223762 THEN 'TempC'
            WHEN c.itemid = 220277 THEN 'SpO2'
        END AS vital_sign,
        c.valuenum
    FROM
        `physionet-data.mimiciv_3_1_icu.chartevents` AS c
    INNER JOIN
        cohort_definition AS cd ON c.stay_id = cd.stay_id
    WHERE
        c.itemid IN (
            220045,
            220179, 220050,
            220052, 225312,
            220210, 224690,
            223762,
            220277
        )
        AND c.charttime BETWEEN cd.intime AND DATETIME_ADD(cd.intime, INTERVAL 48 HOUR)
        AND c.valuenum IS NOT NULL AND c.valuenum > 0
),
vitals_with_abnormal_flags AS (
    SELECT
        stay_id,
        vital_sign,
        valuenum,
        CASE
            WHEN vital_sign = 'HeartRate' AND (valuenum < 50 OR valuenum > 120) THEN 1
            WHEN vital_sign = 'SBP' AND (valuenum < 90 OR valuenum > 180) THEN 1
            WHEN vital_sign = 'MAP' AND valuenum < 65 THEN 1
            WHEN vital_sign = 'RespRate' AND (valuenum < 10 OR valuenum > 30) THEN 1
            WHEN vital_sign = 'TempC' AND (valuenum < 36.0 OR valuenum > 38.5) THEN 1
            WHEN vital_sign = 'SpO2' AND valuenum < 90 THEN 1
            ELSE 0
        END AS is_abnormal
    FROM vitals_first_48h
),
patient_level_scores AS (
    SELECT
        v.stay_id,
        (
            COALESCE(SAFE_DIVIDE(STDDEV(CASE WHEN v.vital_sign = 'HeartRate' THEN v.valuenum END), AVG(CASE WHEN v.vital_sign = 'HeartRate' THEN v.valuenum END)), 0)
            + COALESCE(SAFE_DIVIDE(STDDEV(CASE WHEN v.vital_sign = 'SBP' THEN v.valuenum END), AVG(CASE WHEN v.vital_sign = 'SBP' THEN v.valuenum END)), 0)
            + COALESCE(SAFE_DIVIDE(STDDEV(CASE WHEN v.vital_sign = 'MAP' THEN v.valuenum END), AVG(CASE WHEN v.vital_sign = 'MAP' THEN v.valuenum END)), 0)
            + COALESCE(SAFE_DIVIDE(STDDEV(CASE WHEN v.vital_sign = 'RespRate' THEN v.valuenum END), AVG(CASE WHEN v.vital_sign = 'RespRate' THEN v.valuenum END)), 0)
        ) AS instability_score,
        SUM(v.is_abnormal) AS total_abnormal_episodes,
        AVG(v.is_abnormal) AS proportion_abnormal
    FROM
        vitals_with_abnormal_flags AS v
    GROUP BY
        v.stay_id
)
SELECT
    cd.cohort_group,
    COUNT(DISTINCT cd.stay_id) AS number_of_patients,
    AVG(pls.instability_score) AS avg_instability_score,
    APPROX_QUANTILES(pls.instability_score, 100)[OFFSET(25)] AS p25_instability_score,
    APPROX_QUANTILES(pls.instability_score, 100)[OFFSET(50)] AS p50_instability_score,
    APPROX_QUANTILES(pls.instability_score, 100)[OFFSET(75)] AS p75_instability_score,
    AVG(pls.total_abnormal_episodes) AS avg_abnormal_episodes_count,
    AVG(pls.proportion_abnormal) AS avg_proportion_of_abnormal_vitals,
    AVG(DATETIME_DIFF(cd.outtime, cd.intime, HOUR)) AS avg_icu_los_hours,
    AVG(CAST(cd.hospital_expire_flag AS FLOAT64)) AS mortality_rate
FROM
    cohort_definition AS cd
LEFT JOIN
    patient_level_scores AS pls ON cd.stay_id = pls.stay_id
GROUP BY
    cd.cohort_group
ORDER BY
    cd.cohort_group DESC
