WITH all_admissions_with_next AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_location,
        a.insurance,
        p.gender,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days,
        LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
        a.dischtime IS NOT NULL
),
index_admissions AS (
    SELECT
        adm.hadm_id,
        adm.dischtime,
        adm.los_days,
        adm.next_admittime
    FROM
        all_admissions_with_next AS adm
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON adm.hadm_id = d.hadm_id
    WHERE
        adm.gender = 'F'
        AND adm.age_at_admission BETWEEN 46 AND 56
        AND adm.insurance = 'Medicare'
        AND UPPER(adm.admission_location) LIKE '%TRANSFER%HOSP%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '820%')
            OR (d.icd_version = 10 AND (d.icd_code LIKE 'S72.0%' OR d.icd_code LIKE 'S72.1%' OR d.icd_code LIKE 'S72.2%'))
        )
),
cohort_with_metrics AS (
    SELECT
        idx.hadm_id,
        idx.los_days,
        CASE
            WHEN idx.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(idx.next_admittime), DATE(idx.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30_days
    FROM
        index_admissions AS idx
)
SELECT
    COUNT(*) AS total_cohort_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30_days) * 100.0, COUNT(*)) AS readmission_rate_30_day_percent,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2)[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2)[OFFSET(1)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(COUNTIF(los_days > 7) * 100.0, COUNT(*)) AS percent_los_gt_7_days
FROM
    cohort_with_metrics;
