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
        LEAD(a.admittime) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
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
        END AS is_readmitted_30day
    FROM
        all_admissions_with_next AS adm
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON adm.hadm_id = d.hadm_id
    WHERE
        adm.gender = 'F'
        AND adm.insurance = 'Medicare'
        AND (adm.anchor_age + EXTRACT(YEAR FROM adm.admittime) - adm.anchor_year) BETWEEN 79 AND 89
        AND UPPER(adm.admission_location) LIKE '%EMERGENCY%'
        AND adm.dischtime IS NOT NULL
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '486%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'J18%')
        )
)
SELECT
    COUNT(hadm_id) AS total_cohort_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30day), COUNT(hadm_id)) * 100 AS readmission_rate_30day_pct,
    APPROX_QUANTILES(IF(is_readmitted_30day = 1, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(IF(is_readmitted_30day = 0, los_days, NULL), 100 IGNORE NULLS)[OFFSET(50)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(COUNTIF(los_days > 7), COUNT(hadm_id)) * 100 AS pct_admissions_los_gt_7_days
FROM
    index_admissions;
