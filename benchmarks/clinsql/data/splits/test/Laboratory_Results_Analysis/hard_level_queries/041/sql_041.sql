WITH
age_matched_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        (EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age AS age_at_admission
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'M'
        AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age BETWEEN 54 AND 64
),
hf_cohort_ids AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        hadm_id IN (SELECT hadm_id FROM age_matched_cohort)
        AND (
            (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '428') OR
            (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I50')
        )
),
full_cohort AS (
    SELECT
        amc.subject_id,
        amc.hadm_id,
        amc.admittime,
        amc.dischtime,
        amc.hospital_expire_flag,
        CASE WHEN hfc.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS is_hf_patient
    FROM age_matched_cohort AS amc
    LEFT JOIN hf_cohort_ids AS hfc ON amc.hadm_id = hfc.hadm_id
),
lab_definitions AS (
    SELECT 50983 AS itemid, 'Sodium' AS label, 125.0 AS critical_low, 155.0 AS critical_high UNION ALL
    SELECT 50971, 'Potassium', 2.5, 6.5 UNION ALL
    SELECT 50912, 'Creatinine', NULL, 4.0 UNION ALL
    SELECT 51301, 'WBC', 2.0, 30.0 UNION ALL
    SELECT 51265, 'Platelet Count', 20.0, NULL UNION ALL
    SELECT 50813, 'Lactate', NULL, 4.0 UNION ALL
    SELECT 50820, 'pH', 7.20, 7.60
),
first_48h_labs AS (
    SELECT
        fc.hadm_id,
        le.itemid,
        le.valuenum
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN full_cohort AS fc ON le.hadm_id = fc.hadm_id
    WHERE
        DATETIME_DIFF(le.charttime, fc.admittime, HOUR) BETWEEN 0 AND 48
        AND le.valuenum IS NOT NULL
        AND le.itemid IN (SELECT itemid FROM lab_definitions)
),
instability_scores AS (
    SELECT
        f48l.hadm_id,
        COUNT(DISTINCT ld.itemid) AS instability_score
    FROM first_48h_labs AS f48l
    INNER JOIN lab_definitions AS ld ON f48l.itemid = ld.itemid
    WHERE
        (f48l.valuenum < ld.critical_low) OR
        (f48l.valuenum > ld.critical_high)
    GROUP BY f48l.hadm_id
),
cohort_with_scores AS (
    SELECT
        fc.hadm_id,
        fc.is_hf_patient,
        fc.hospital_expire_flag,
        DATETIME_DIFF(fc.dischtime, fc.admittime, DAY) AS los_days,
        COALESCE(sc.instability_score, 0) AS instability_score
    FROM full_cohort AS fc
    LEFT JOIN instability_scores AS sc ON fc.hadm_id = sc.hadm_id
),
hf_p95_threshold AS (
    SELECT
        APPROX_QUANTILES(instability_score, 100)[OFFSET(95)] AS p95_score
    FROM cohort_with_scores
    WHERE is_hf_patient = 1
),
patient_groups AS (
    SELECT
        cws.hadm_id,
        cws.hospital_expire_flag,
        cws.los_days,
        CASE
            WHEN cws.is_hf_patient = 1 AND cws.instability_score >= (SELECT p95_score FROM hf_p95_threshold)
            THEN 'Top Tier HF (>=P95)'
            ELSE NULL
        END AS hf_tier,
        'Age-Matched Control (All M, 54-64)' AS control_tier
    FROM cohort_with_scores AS cws
),
top_tier_hf_outcomes AS (
    SELECT
        'Top Tier HF (>=P95)' AS patient_group,
        AVG(hospital_expire_flag) AS mortality_rate,
        AVG(los_days) AS avg_los_days
    FROM patient_groups
    WHERE hf_tier IS NOT NULL
    GROUP BY patient_group
),
critical_lab_rates AS (
    SELECT
        'Top Tier HF (>=P95)' AS patient_group,
        SAFE_DIVIDE(
            COUNTIF((f48l.valuenum < ld.critical_low) OR (f48l.valuenum > ld.critical_high)),
            COUNT(f48l.itemid)
        ) AS critical_lab_rate
    FROM first_48h_labs AS f48l
    INNER JOIN lab_definitions AS ld ON f48l.itemid = ld.itemid
    WHERE f48l.hadm_id IN (SELECT hadm_id FROM patient_groups WHERE hf_tier IS NOT NULL)
    UNION ALL
    SELECT
        'Age-Matched Control (All M, 54-64)' AS patient_group,
        SAFE_DIVIDE(
            COUNTIF((f48l.valuenum < ld.critical_low) OR (f48l.valuenum > ld.critical_high)),
            COUNT(f48l.itemid)
        ) AS critical_lab_rate
    FROM first_48h_labs AS f48l
    INNER JOIN lab_definitions AS ld ON f48l.itemid = ld.itemid
)
SELECT
    'P95 Instability Score Threshold for HF Cohort' AS metric,
    CAST(p95_score AS STRING) AS value,
    'The instability score at the 95th percentile for male HF patients aged 54-64.' AS description
FROM hf_p95_threshold
UNION ALL
SELECT
    'In-Hospital Mortality Rate' AS metric,
    CAST(ROUND(mortality_rate * 100, 2) AS STRING) || '%' AS value,
    'For Top Tier HF (>=P95) group.' AS description
FROM top_tier_hf_outcomes
UNION ALL
SELECT
    'Average Length of Stay (Days)' AS metric,
    CAST(ROUND(avg_los_days, 1) AS STRING) AS value,
    'For Top Tier HF (>=P95) group.' AS description
FROM top_tier_hf_outcomes
UNION ALL
SELECT
    'Critical Lab Rate' AS metric,
    CAST(ROUND(critical_lab_rate * 100, 2) AS STRING) || '%' AS value,
    'For ' || patient_group || ' group. (Rate of critical results among labs measured).' AS description
FROM critical_lab_rates
ORDER BY
    CASE
        WHEN metric LIKE 'P95%' THEN 1
        WHEN metric LIKE 'In-Hospital%' THEN 2
        WHEN metric LIKE 'Average%' THEN 3
        WHEN metric LIKE 'Critical%' THEN 4
    END,
    description;
