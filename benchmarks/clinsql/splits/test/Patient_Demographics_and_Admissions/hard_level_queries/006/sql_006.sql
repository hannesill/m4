WITH all_admissions_with_lead AS (
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
        a.hadm_id,
        a.subject_id,
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
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 36 AND 46
        AND a.insurance = 'Medicare'
        AND UPPER(a.admission_location) LIKE '%TRANSFER%HOSP%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) IN ('430', '431', '432'))
            OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('I60', 'I61', 'I62'))
        )
        AND a.dischtime IS NOT NULL
),
cohort_with_readmission_flag AS (
    SELECT
        i.hadm_id,
        i.los_days,
        CASE
            WHEN l.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(l.next_admittime), DATE(i.dischtime), DAY) <= 30
                THEN 1
            ELSE 0
        END AS is_readmitted_30_day
    FROM index_admissions AS i
    LEFT JOIN all_admissions_with_lead AS l
        ON i.hadm_id = l.hadm_id
)
SELECT
    COUNT(hadm_id) AS total_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30_day), COUNT(hadm_id)) * 100 AS readmission_rate_30_day_percent,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_day = 1 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_day = 0 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_non_readmitted_days,
    SAFE_DIVIDE(
        COUNTIF(los_days > 7), COUNT(hadm_id)
    ) * 100 AS percent_los_gt_7_days
FROM cohort_with_readmission_flag;
