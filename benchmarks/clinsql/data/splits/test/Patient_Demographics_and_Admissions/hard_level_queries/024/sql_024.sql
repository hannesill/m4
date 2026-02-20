WITH
all_admissions_with_lead AS (
    SELECT
        subject_id,
        hadm_id,
        admittime,
        dischtime,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions`
),
index_cohort AS (
    SELECT
        a.hadm_id,
        a.subject_id,
        a.admittime,
        a.dischtime,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 76 AND 86
        AND a.insurance = 'Medicare'
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '434%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I63%')
        )
        AND a.dischtime IS NOT NULL
),
cohort_with_readmission_flag AS (
    SELECT
        idx.hadm_id,
        idx.los_days,
        CASE
            WHEN leads.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(leads.next_admittime), DATE(idx.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30_days
    FROM
        index_cohort AS idx
    INNER JOIN all_admissions_with_lead AS leads
        ON idx.hadm_id = leads.hadm_id
)
SELECT
    AVG(is_readmitted_30_days) * 100 AS readmission_rate_30_day_percent,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 100
    )[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 100
    )[OFFSET(50)] AS median_los_not_readmitted_days,
    AVG(CASE WHEN los_days > 5 THEN 1.0 ELSE 0.0 END) * 100 AS percent_los_gt_5_days
FROM
    cohort_with_readmission_flag;
