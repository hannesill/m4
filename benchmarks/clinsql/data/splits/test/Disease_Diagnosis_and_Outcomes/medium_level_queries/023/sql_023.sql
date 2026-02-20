WITH patient_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.hospital_expire_flag,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS length_of_stay
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 52 AND 62
        AND a.admittime IS NOT NULL
        AND a.dischtime IS NOT NULL
),
admission_diagnoses AS (
    SELECT
        pc.hadm_id,
        pc.length_of_stay,
        pc.hospital_expire_flag,
        MAX(CASE
            WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) IN ('433', '434') THEN 1
            WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) = 'I63' THEN 1
            ELSE 0
        END) AS is_ischemic_stroke,
        MAX(CASE
            WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) IN ('430', '431', '432') THEN 1
            WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('I60', 'I61', 'I62') THEN 1
            ELSE 0
        END) AS is_hemorrhagic_stroke,
        MAX(CASE
            WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '585' THEN 1
            WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) = 'N18' THEN 1
            ELSE 0
        END) AS has_ckd,
        MAX(CASE
            WHEN d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '250' THEN 1
            WHEN d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('E08', 'E09', 'E10', 'E11', 'E13') THEN 1
            ELSE 0
        END) AS has_diabetes,
        COUNT(DISTINCT d.icd_code) AS comorbidity_count
    FROM
        patient_cohort AS pc
    JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON pc.hadm_id = d.hadm_id
    GROUP BY
        pc.hadm_id, pc.length_of_stay, pc.hospital_expire_flag
),
categorized_admissions AS (
    SELECT
        hadm_id,
        length_of_stay,
        hospital_expire_flag,
        has_ckd,
        has_diabetes,
        CASE
            WHEN is_ischemic_stroke = 1 THEN 'Ischemic'
            WHEN is_hemorrhagic_stroke = 1 THEN 'Hemorrhagic'
        END AS stroke_type,
        CASE
            WHEN length_of_stay < 8 THEN '< 8 Days'
            ELSE '>= 8 Days'
        END AS los_category,
        CASE NTILE(3) OVER (PARTITION BY
                                CASE
                                    WHEN is_ischemic_stroke = 1 THEN 'Ischemic'
                                    WHEN is_hemorrhagic_stroke = 1 THEN 'Hemorrhagic'
                                END
                            ORDER BY comorbidity_count)
            WHEN 1 THEN 'Low'
            WHEN 2 THEN 'Medium'
            WHEN 3 THEN 'High'
        END AS comorbidity_burden
    FROM
        admission_diagnoses
    WHERE
        (is_ischemic_stroke = 1 AND is_hemorrhagic_stroke = 0)
        OR (is_hemorrhagic_stroke = 1 AND is_ischemic_stroke = 0)
)
SELECT
    stroke_type,
    los_category,
    comorbidity_burden,
    COUNT(*) AS total_admissions,
    ROUND(AVG(hospital_expire_flag) * 100.0, 2) AS mortality_rate_percent,
    APPROX_QUANTILES(length_of_stay, 2)[OFFSET(1)] AS median_length_of_stay,
    ROUND(AVG(has_ckd) * 100.0, 2) AS ckd_prevalence_percent,
    ROUND(AVG(has_diabetes) * 100.0, 2) AS diabetes_prevalence_percent
FROM
    categorized_admissions
GROUP BY
    stroke_type,
    los_category,
    comorbidity_burden
ORDER BY
    stroke_type,
    CASE comorbidity_burden
        WHEN 'Low' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'High' THEN 3
    END,
    los_category;
