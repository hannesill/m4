WITH all_admissions_with_next AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_location,
        a.insurance,
        p.gender,
        (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
        LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
),
index_admissions AS (
    SELECT
        adm.hadm_id,
        adm.dischtime,
        adm.next_admittime,
        DATETIME_DIFF(adm.dischtime, adm.admittime, HOUR) / 24.0 AS los_days,
        CASE
            WHEN adm.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(adm.next_admittime), DATE(adm.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30d
    FROM
        all_admissions_with_next AS adm
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON adm.hadm_id = d.hadm_id
    WHERE
        adm.gender = 'M'
        AND adm.age_at_admission BETWEEN 43 AND 53
        AND adm.insurance = 'Medicare'
        AND (
            UPPER(adm.admission_location) LIKE '%SKILLED NURSING%'
            OR UPPER(adm.admission_location) LIKE '%SNF%'
        )
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code = '27651')
            OR (d.icd_version = 10 AND d.icd_code = 'E860')
        )
        AND adm.dischtime IS NOT NULL
)
SELECT
    COUNT(hadm_id) AS total_cohort_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30d), COUNT(hadm_id)) * 100 AS readmission_rate_30d_pct,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30d = 1 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30d = 0 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(
        SUM(CASE WHEN los_days > 7 THEN 1 ELSE 0 END),
        COUNT(hadm_id)
    ) * 100 AS pct_los_gt_7_days
FROM
    index_admissions;
