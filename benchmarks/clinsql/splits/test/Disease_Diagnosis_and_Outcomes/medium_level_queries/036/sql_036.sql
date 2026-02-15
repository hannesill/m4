WITH
base_admissions AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code LIKE '428%'
                OR d.icd_code LIKE 'I50%'
            )
        )
),
diag_counts AS (
    SELECT
        b.hadm_id,
        b.hospital_expire_flag,
        b.los_days,
        COUNT(DISTINCT d.icd_code) AS diagnosis_count
    FROM
        base_admissions AS b
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON b.hadm_id = d.hadm_id
    GROUP BY
        b.hadm_id, b.hospital_expire_flag, b.los_days
),
tertile_boundaries AS (
    SELECT
        boundaries[OFFSET(1)] AS t1,
        boundaries[OFFSET(2)] AS t2
    FROM (
        SELECT APPROX_QUANTILES(diagnosis_count, 3) AS boundaries
        FROM diag_counts
    )
),
cohort_with_strata AS (
    SELECT
        dc.hadm_id,
        dc.hospital_expire_flag,
        CASE
            WHEN dc.los_days <= 5 THEN '<=5 days'
            ELSE '>5 days'
        END AS los_group,
        CASE
            WHEN dc.diagnosis_count <= tb.t1 THEN 'Low'
            WHEN dc.diagnosis_count > tb.t1 AND dc.diagnosis_count <= tb.t2 THEN 'Medium'
            ELSE 'High'
        END AS comorbidity_burden,
        EXISTS (
            SELECT 1 FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = dc.hadm_id AND (d.icd_code LIKE '585%' OR d.icd_code LIKE 'N18%')
        ) AS has_ckd,
        EXISTS (
            SELECT 1 FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = dc.hadm_id AND (d.icd_code LIKE '250%' OR d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%')
        ) AS has_diabetes
    FROM
        diag_counts AS dc,
        tertile_boundaries AS tb
),
all_strata AS (
    SELECT
        los_group,
        comorbidity_burden
    FROM
        (SELECT * FROM UNNEST(['<=5 days', '>5 days']) AS los_group)
    CROSS JOIN
        (SELECT * FROM UNNEST(['Low', 'Medium', 'High']) AS comorbidity_burden)
)
SELECT
    s.los_group,
    s.comorbidity_burden,
    COUNT(c.hadm_id) AS N,
    ROUND(SAFE_DIVIDE(SUM(c.hospital_expire_flag), COUNT(c.hadm_id)) * 100, 2) AS mortality_rate_pct,
    ROUND(SAFE_DIVIDE(SUM(CAST(c.has_ckd AS INT64)), COUNT(c.hadm_id)) * 100, 2) AS ckd_prevalence_pct,
    ROUND(SAFE_DIVIDE(SUM(CAST(c.has_diabetes AS INT64)), COUNT(c.hadm_id)) * 100, 2) AS diabetes_prevalence_pct
FROM
    all_strata AS s
LEFT JOIN
    cohort_with_strata AS c
    ON s.los_group = c.los_group AND s.comorbidity_burden = c.comorbidity_burden
GROUP BY
    s.los_group, s.comorbidity_burden
ORDER BY
    s.los_group,
    CASE s.comorbidity_burden
        WHEN 'Low' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'High' THEN 3
    END;
