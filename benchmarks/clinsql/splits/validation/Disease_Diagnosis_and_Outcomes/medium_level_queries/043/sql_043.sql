WITH cohort_base AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 44 AND 54
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
            WHERE dx.hadm_id = a.hadm_id
            AND (
                dx.icd_code LIKE '428%'
                OR dx.icd_code LIKE 'I50%'
            )
        )
),
organ_support AS (
    SELECT
        pe.hadm_id,
        MAX(CASE WHEN pe.itemid IN (
            225792,
            225794
        ) THEN 1 ELSE 0 END) AS flag_mech_vent,
        MAX(CASE WHEN pe.itemid IN (
            221906,
            221289,
            222315,
            221749
        ) THEN 1 ELSE 0 END) AS flag_vasopressor,
        MAX(CASE WHEN pe.itemid IN (
            225802,
            225803,
            225805,
            225807
        ) THEN 1 ELSE 0 END) AS flag_rrt
    FROM `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
    GROUP BY pe.hadm_id
),
cohort_features AS (
    SELECT
        c.hadm_id,
        c.hospital_expire_flag,
        CASE WHEN icu.hadm_id IS NOT NULL THEN 'Higher-Severity (ICU)' ELSE 'Lower-Severity (No ICU)' END AS severity_group,
        CASE WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) <= 7 THEN '<=7 days' ELSE '>7 days' END AS los_group,
        CASE
            WHEN COALESCE(ch.charlson_comorbidity_index, 0) <= 1 THEN '0-1'
            WHEN COALESCE(ch.charlson_comorbidity_index, 0) = 2 THEN '2'
            ELSE '>=3'
        END AS comorbidity_group,
        COALESCE(os.flag_mech_vent, 0) AS flag_mech_vent,
        COALESCE(os.flag_vasopressor, 0) AS flag_vasopressor,
        COALESCE(os.flag_rrt, 0) AS flag_rrt
    FROM cohort_base AS c
    LEFT JOIN (SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
        ON c.hadm_id = icu.hadm_id
    LEFT JOIN `physionet-data.mimiciv_3_1_derived.charlson` AS ch
        ON c.hadm_id = ch.hadm_id
    LEFT JOIN organ_support AS os
        ON c.hadm_id = os.hadm_id
),
all_strata AS (
    SELECT
        severity_group,
        los_group,
        comorbidity_group
    FROM
        (SELECT severity_group FROM UNNEST(['Higher-Severity (ICU)', 'Lower-Severity (No ICU)']) AS severity_group)
    CROSS JOIN
        (SELECT los_group FROM UNNEST(['<=7 days', '>7 days']) AS los_group)
    CROSS JOIN
        (SELECT comorbidity_group FROM UNNEST(['0-1', '2', '>=3']) AS comorbidity_group)
)
SELECT
    s.severity_group,
    s.los_group,
    s.comorbidity_group,
    COUNT(c.hadm_id) AS number_of_admissions,
    ROUND(SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id)) * 100, 2) AS mortality_rate_pct,
    ROUND(
        (
            SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id)) + (1.96*1.96)/(2*COUNT(c.hadm_id))
            - 1.96 * SQRT(
                (SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id)) * (1 - SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id))) / COUNT(c.hadm_id))
                + (1.96*1.96)/(4*COUNT(c.hadm_id)*COUNT(c.hadm_id))
            )
        ) / (1 + (1.96*1.96)/COUNT(c.hadm_id)) * 100
    , 2) AS mortality_rate_ci95_lower,
    ROUND(
        (
            SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id)) + (1.96*1.96)/(2*COUNT(c.hadm_id))
            + 1.96 * SQRT(
                (SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id)) * (1 - SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id))) / COUNT(c.hadm_id))
                + (1.96*1.96)/(4*COUNT(c.hadm_id)*COUNT(c.hadm_id))
            )
        ) / (1 + (1.96*1.96)/COUNT(c.hadm_id)) * 100
    , 2) AS mortality_rate_ci95_upper,
    ROUND(AVG(c.flag_mech_vent) * 100, 2) AS mech_vent_prevalence_pct,
    ROUND(AVG(c.flag_vasopressor) * 100, 2) AS vasopressor_prevalence_pct,
    ROUND(AVG(c.flag_rrt) * 100, 2) AS rrt_prevalence_pct
FROM
    all_strata AS s
LEFT JOIN
    cohort_features AS c
    ON s.severity_group = c.severity_group
    AND s.los_group = c.los_group
    AND s.comorbidity_group = c.comorbidity_group
GROUP BY
    s.severity_group,
    s.los_group,
    s.comorbidity_group
ORDER BY
    s.severity_group DESC,
    s.los_group,
    CASE
        WHEN s.comorbidity_group = '0-1' THEN 1
        WHEN s.comorbidity_group = '2' THEN 2
        WHEN s.comorbidity_group = '>=3' THEN 3
    END;
