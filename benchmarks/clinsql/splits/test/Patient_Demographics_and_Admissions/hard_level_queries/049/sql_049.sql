WITH all_subject_admissions AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_location,
        a.insurance,
        p.gender,
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission,
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
        END AS is_readmitted_30_days
    FROM
        all_subject_admissions AS aa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON aa.hadm_id = d.hadm_id
    WHERE
        aa.gender = 'F'
        AND aa.age_at_admission BETWEEN 61 AND 71
        AND aa.insurance = 'Medicare'
        AND (
            UPPER(aa.admission_location) LIKE '%SKILLED NURSING%'
            OR UPPER(aa.admission_location) LIKE '%SNF%'
        )
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '584%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'N17%')
        )
        AND aa.dischtime IS NOT NULL
)
SELECT
    100.0 * AVG(idx.is_readmitted_30_days) AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(
        CASE WHEN idx.is_readmitted_30_days = 1 THEN idx.los_days END, 2
    )[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(
        CASE WHEN idx.is_readmitted_30_days = 0 THEN idx.los_days END, 2
    )[OFFSET(1)] AS median_los_not_readmitted_days,
    100.0 * AVG(CASE WHEN idx.los_days > 6 THEN 1 ELSE 0 END) AS pct_index_los_gt_6_days
FROM
    index_admissions AS idx;
