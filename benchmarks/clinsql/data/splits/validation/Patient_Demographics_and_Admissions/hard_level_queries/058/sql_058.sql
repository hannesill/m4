WITH all_admissions_with_next AS (
    SELECT
        subject_id,
        hadm_id,
        admittime,
        dischtime,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions`
),
index_admissions AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        a.admittime,
        a.dischtime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 50 AND 60
        AND a.insurance = 'Medicare'
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND a.dischtime IS NOT NULL
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code IN ('5781', '5693'))
            OR (d.icd_version = 10 AND d.icd_code IN ('K921', 'K922', 'K625'))
        )
),
readmission_cohort AS (
    SELECT
        ia.hadm_id,
        DATETIME_DIFF(ia.dischtime, ia.admittime, HOUR) / 24.0 AS index_los_days,
        CASE
            WHEN next.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(next.next_admittime), DATE(ia.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30_day
    FROM
        index_admissions AS ia
    LEFT JOIN
        all_admissions_with_next AS next
        ON ia.hadm_id = next.hadm_id
)
SELECT
    SAFE_DIVIDE(SUM(is_readmitted_30_day), COUNT(*)) * 100 AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_day = 1 THEN index_los_days END, 100)[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_day = 0 THEN index_los_days END, 100)[OFFSET(50)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(COUNTIF(index_los_days > 6), COUNT(*)) * 100 AS pct_index_los_gt_6_days
FROM
    readmission_cohort;
