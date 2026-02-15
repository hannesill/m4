WITH
admissions_ranked AS (
    SELECT
        hadm_id,
        subject_id,
        admittime,
        dischtime,
        admission_location,
        insurance,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
),
cohort_with_readmission AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days,
        CASE
            WHEN a.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(a.next_admittime), DATE(a.dischtime), DAY) <= 30
                THEN 1
            ELSE 0
        END AS is_readmitted_30d
    FROM admissions_ranked AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND a.insurance = 'Medicare'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 43 AND 53
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            d.icd_code LIKE '2501%'
            OR d.icd_code LIKE 'E101%'
            OR d.icd_code LIKE 'E111%'
            OR d.icd_code LIKE 'E131%'
        )
        AND a.dischtime IS NOT NULL
)
SELECT
    COUNT(hadm_id) AS total_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30d), COUNT(hadm_id)) * 100 AS readmission_rate_30d_pct,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30d = 0 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_not_readmitted,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30d = 1 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_readmitted,
    SAFE_DIVIDE(
        SUM(CASE WHEN los_days > 7.0 THEN 1 ELSE 0 END), COUNT(hadm_id)
    ) * 100 AS pct_los_gt_7_days
FROM cohort_with_readmission;
