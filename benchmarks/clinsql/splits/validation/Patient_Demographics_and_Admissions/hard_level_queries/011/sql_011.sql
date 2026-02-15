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
                 AND aa.next_admittime > aa.dischtime
                 AND DATE_DIFF(DATE(aa.next_admittime), DATE(aa.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted_30d
    FROM
        all_admissions_with_next AS aa
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON aa.hadm_id = d.hadm_id
    WHERE
        aa.gender = 'F'
        AND (aa.anchor_age + EXTRACT(YEAR FROM aa.admittime) - aa.anchor_year) BETWEEN 68 AND 78
        AND aa.insurance = 'Medicare'
        AND UPPER(aa.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '430%' OR d.icd_code LIKE '431%' OR d.icd_code LIKE '432%'))
            OR
            (d.icd_version = 10 AND (d.icd_code LIKE 'I60%' OR d.icd_code LIKE 'I61%' OR d.icd_code LIKE 'I62%'))
        )
        AND aa.dischtime IS NOT NULL
)
SELECT
    COUNT(hadm_id) AS total_admissions,
    SAFE_DIVIDE(SUM(is_readmitted_30d) * 100.0, COUNT(hadm_id)) AS readmission_rate_30d_pct,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30d = 1 THEN los_days END, 2)[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(CASE WHEN is_readmitted_30d = 0 THEN los_days END, 2)[OFFSET(1)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(COUNTIF(los_days > 7) * 100.0, COUNT(hadm_id)) AS pct_los_gt_7_days
FROM
    index_admissions;
