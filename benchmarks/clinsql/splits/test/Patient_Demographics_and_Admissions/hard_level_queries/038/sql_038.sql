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
), index_admissions AS (
    SELECT
        aa.*
    FROM
        all_admissions_with_next AS aa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON aa.hadm_id = d.hadm_id
    WHERE
        aa.gender = 'M'
        AND aa.age_at_admission BETWEEN 90 AND 100
        AND aa.insurance = 'Medicare'
        AND UPPER(aa.admission_location) LIKE '%TRANSFER%HOSP%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code = '5856')
            OR (d.icd_version = 10 AND d.icd_code = 'N186')
        )
), readmission_cohort AS (
    SELECT
        ia.hadm_id,
        ia.los_days,
        CASE
            WHEN ia.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(ia.next_admittime), DATE(ia.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted
    FROM
        index_admissions AS ia
)
SELECT
    COUNT(*) AS total_admissions_in_cohort,
    SAFE_DIVIDE(SUM(is_readmitted), COUNT(*)) * 100 AS readmission_rate_30_day_percent,
    APPROX_QUANTILES(IF(is_readmitted = 1, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(IF(is_readmitted = 0, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_los_non_readmitted_days,
    SAFE_DIVIDE(SUM(IF(los_days > 7, 1, 0)), COUNT(*)) * 100 AS percent_los_gt_7_days
FROM
    readmission_cohort;
