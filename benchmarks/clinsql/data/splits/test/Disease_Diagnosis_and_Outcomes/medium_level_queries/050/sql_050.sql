WITH base_cohort AS (
    SELECT
        p.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.hospital_expire_flag
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 75 AND 85
        AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code = '99591'
                OR d.icd_code LIKE 'A41%'
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
            WHERE d.hadm_id = a.hadm_id
            AND (
                d.icd_code = '78552'
                OR d.icd_code = 'R6521'
            )
        )
),
cohort_with_features AS (
    SELECT
        c.hadm_id,
        c.hospital_expire_flag,
        CASE
            WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) <= 5 THEN '<=5 days'
            ELSE '>5 days'
        END AS los_group,
        EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = c.hadm_id
            AND (d.icd_code LIKE '585%' OR d.icd_code LIKE 'N18%')
        ) AS has_ckd,
        EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = c.hadm_id
            AND (
                d.icd_code LIKE '250%'
                OR d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%'
                OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%'
                OR d.icd_code LIKE 'E13%'
            )
        ) AS has_diabetes,
        EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = c.hadm_id
            AND (d.icd_code = '42731' OR d.icd_code LIKE 'I48%')
        ) AS has_afib,
        EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d
            WHERE d.hadm_id = c.hadm_id
            AND (d.icd_code LIKE '401%' OR d.icd_code = 'I10')
        ) AS has_htn
    FROM
        base_cohort AS c
)
SELECT
    los_group,
    COUNT(hadm_id) AS number_of_admissions,
    COUNTIF(has_ckd) AS n_with_ckd,
    ROUND(
        SAFE_DIVIDE(COUNTIF(has_ckd AND hospital_expire_flag = 1), COUNTIF(has_ckd)) * 100, 2
    ) AS mortality_rate_with_ckd_pct,
    COUNTIF(NOT has_ckd) AS n_without_ckd,
    ROUND(
        SAFE_DIVIDE(COUNTIF(NOT has_ckd AND hospital_expire_flag = 1), COUNTIF(NOT has_ckd)) * 100, 2
    ) AS mortality_rate_without_ckd_pct,
    COUNTIF(has_diabetes) AS n_with_diabetes,
    ROUND(
        SAFE_DIVIDE(COUNTIF(has_diabetes AND hospital_expire_flag = 1), COUNTIF(has_diabetes)) * 100, 2
    ) AS mortality_rate_with_diabetes_pct,
    COUNTIF(NOT has_diabetes) AS n_without_diabetes,
    ROUND(
        SAFE_DIVIDE(COUNTIF(NOT has_diabetes AND hospital_expire_flag = 1), COUNTIF(NOT has_diabetes)) * 100, 2
    ) AS mortality_rate_without_diabetes_pct,
    COUNTIF(has_afib) AS n_with_afib,
    ROUND(
        SAFE_DIVIDE(COUNTIF(has_afib AND hospital_expire_flag = 1), COUNTIF(has_afib)) * 100, 2
    ) AS mortality_rate_with_afib_pct,
    COUNTIF(NOT has_afib) AS n_without_afib,
    ROUND(
        SAFE_DIVIDE(COUNTIF(NOT has_afib AND hospital_expire_flag = 1), COUNTIF(NOT has_afib)) * 100, 2
    ) AS mortality_rate_without_afib_pct,
    COUNTIF(has_htn) AS n_with_htn,
    ROUND(
        SAFE_DIVIDE(COUNTIF(has_htn AND hospital_expire_flag = 1), COUNTIF(has_htn)) * 100, 2
    ) AS mortality_rate_with_htn_pct,
    COUNTIF(NOT has_htn) AS n_without_htn,
    ROUND(
        SAFE_DIVIDE(COUNTIF(NOT has_htn AND hospital_expire_flag = 1), COUNTIF(NOT has_htn)) * 100, 2
    ) AS mortality_rate_without_htn_pct
FROM
    cohort_with_features
GROUP BY
    los_group
ORDER BY
    CASE
        WHEN los_group = '<=5 days' THEN 1
        WHEN los_group = '>5 days' THEN 2
        ELSE 3
    END;
