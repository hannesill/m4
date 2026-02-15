WITH all_admissions_with_next AS (
    SELECT
        p.subject_id,
        p.gender,
        p.anchor_age,
        p.anchor_year,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        a.admission_location,
        a.insurance,
        LEAD(a.admittime, 1) OVER (PARTITION BY p.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
),
index_admissions AS (
    SELECT
        all_adm.hadm_id,
        DATETIME_DIFF(all_adm.dischtime, all_adm.admittime, HOUR) / 24.0 AS los_days,
        CASE
            WHEN all_adm.next_admittime IS NOT NULL
                 AND DATE_DIFF(DATE(all_adm.next_admittime), DATE(all_adm.dischtime), DAY) <= 30
                THEN 1
            ELSE 0
        END AS is_readmitted_30_days
    FROM
        all_admissions_with_next AS all_adm
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON all_adm.hadm_id = d.hadm_id
    WHERE
        all_adm.gender = 'M'
        AND (all_adm.anchor_age + EXTRACT(YEAR FROM all_adm.admittime) - all_adm.anchor_year) BETWEEN 60 AND 70
        AND all_adm.insurance = 'Medicare'
        AND UPPER(all_adm.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            d.icd_code LIKE '5990%'
            OR d.icd_code LIKE 'N390%'
        )
        AND all_adm.dischtime IS NOT NULL
)
SELECT
    AVG(is_readmitted_30_days) * 100 AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_days_readmitted,
    APPROX_QUANTILES(
        CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2
    )[OFFSET(1)] AS median_los_days_not_readmitted,
    AVG(CASE WHEN los_days > 9 THEN 1.0 ELSE 0.0 END) * 100 AS pct_index_los_gt_9_days
FROM
    index_admissions;
