WITH all_admissions_with_next AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_location,
        a.insurance,
        p.gender,
        p.anchor_age,
        p.anchor_year,
        LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
),
index_admissions AS (
    SELECT
        aa.hadm_id,
        DATETIME_DIFF(aa.dischtime, aa.admittime, HOUR) / 24.0 AS los_days,
        CASE
            WHEN aa.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(aa.next_admittime), DATE(aa.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30_day
    FROM
        all_admissions_with_next AS aa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON aa.hadm_id = d.hadm_id
    WHERE
        aa.gender = 'M'
        AND (aa.anchor_age + EXTRACT(YEAR FROM aa.admittime) - aa.anchor_year) BETWEEN 51 AND 61
        AND aa.insurance = 'Medicare'
        AND UPPER(aa.admission_location) LIKE '%EMERGENCY%'
        AND aa.dischtime IS NOT NULL
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '5770%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
        )
)
SELECT
    AVG(is_readmitted_30_day) * 100.0 AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(IF(is_readmitted_30_day = 1, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(IF(is_readmitted_30_day = 0, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_los_not_readmitted_days,
    COUNTIF(los_days > 9) * 100.0 / COUNT(*) AS pct_index_los_gt_9_days
FROM
    index_admissions;
