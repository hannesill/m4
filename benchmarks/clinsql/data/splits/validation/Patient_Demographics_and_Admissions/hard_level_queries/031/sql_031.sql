WITH all_admissions AS (
    SELECT
        subject_id,
        hadm_id,
        admittime,
        dischtime,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
),
index_admissions AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 62 AND 72
        AND a.insurance = 'Medicare'
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code = '7802')
            OR (d.icd_version = 10 AND d.icd_code = 'R55')
        )
        AND a.dischtime IS NOT NULL
),
readmission_cohort AS (
    SELECT
        i.hadm_id,
        i.los_days,
        CASE
            WHEN aa.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(aa.next_admittime), DATE(i.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30_days
    FROM index_admissions AS i
    INNER JOIN all_admissions AS aa
        ON i.hadm_id = aa.hadm_id
)
SELECT
    COUNT(hadm_id) AS total_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30_days) * 100.0, COUNT(hadm_id)) AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 100)[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 100)[OFFSET(50)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(
        SUM(CASE WHEN los_days > 7.0 THEN 1 ELSE 0 END) * 100.0,
        COUNT(hadm_id)
    ) AS pct_admissions_los_gt_7_days
FROM readmission_cohort;
