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
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS index_los_days,
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
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 65 AND 75
        AND a.insurance = 'Medicare'
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code = '51881')
            OR
            (d.icd_version = 10 AND d.icd_code LIKE 'J960%')
        )
        AND a.dischtime IS NOT NULL
)
SELECT
    AVG(is_readmitted_30_days) * 100.0 AS readmission_rate_30_day_percent,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_days = 1 THEN index_los_days END, 2
    )[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_days = 0 THEN index_los_days END, 2
    )[OFFSET(1)] AS median_los_not_readmitted_days,
    AVG(CASE WHEN index_los_days > 9 THEN 1 ELSE 0 END) * 100.0 AS percent_los_exceeding_9_days
FROM
    index_admissions;
