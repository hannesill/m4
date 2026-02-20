WITH all_admissions_with_next AS (
    SELECT
        subject_id,
        hadm_id,
        admittime,
        dischtime,
        admission_location,
        insurance,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions`
),
index_admissions AS (
    SELECT
        a.hadm_id,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days,
        CASE
            WHEN a.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(a.next_admittime), DATE(a.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30_days
    FROM
        all_admissions_with_next AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 38 AND 48
        AND a.insurance = 'Medicare'
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code = '5750')
            OR (d.icd_version = 10 AND d.icd_code = 'K810')
        )
        AND a.dischtime IS NOT NULL
)
SELECT
    COUNT(hadm_id) AS total_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30_days), COUNT(hadm_id)) * 100 AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2)[SAFE_OFFSET(1)] AS median_los_readmitted,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2)[SAFE_OFFSET(1)] AS median_los_not_readmitted,
    SAFE_DIVIDE(COUNTIF(los_days > 7), COUNT(hadm_id)) * 100 AS pct_los_gt_7_days
FROM
    index_admissions;
