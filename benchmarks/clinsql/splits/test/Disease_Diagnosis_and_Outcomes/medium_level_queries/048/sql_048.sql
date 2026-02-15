WITH cohort AS (
    SELECT
        a.hadm_id,
        a.hospital_expire_flag,
        DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days,
        CAST(EXISTS(
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_comorb
            WHERE d_comorb.hadm_id = a.hadm_id
              AND (
                d_comorb.icd_code LIKE '585%'
                OR d_comorb.icd_code LIKE 'N18%'
              )
        ) AS INT64) AS has_ckd,
        CAST(EXISTS(
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` d_comorb
            WHERE d_comorb.hadm_id = a.hadm_id
              AND (
                d_comorb.icd_code LIKE '250%'
                OR SUBSTR(d_comorb.icd_code, 1, 3) BETWEEN 'E08' AND 'E13'
              )
        ) AS INT64) AS has_diabetes
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 68 AND 78
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
stratified_cohort AS (
    SELECT
        hadm_id,
        hospital_expire_flag,
        has_ckd,
        has_diabetes,
        CASE
            WHEN los_days < 8 THEN '<8 days'
            ELSE '>=8 days'
        END AS los_stratum
    FROM cohort
)
SELECT
    los_stratum,
    COUNT(hadm_id) AS N,
    ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
    ROUND(AVG(has_ckd) * 100, 2) AS ckd_prevalence_pct,
    ROUND(AVG(has_diabetes) * 100, 2) AS diabetes_prevalence_pct
FROM
    stratified_cohort
GROUP BY
    los_stratum
ORDER BY
    CASE
        WHEN los_stratum = '<8 days' THEN 1
        WHEN los_stratum = '>=8 days' THEN 2
    END;
