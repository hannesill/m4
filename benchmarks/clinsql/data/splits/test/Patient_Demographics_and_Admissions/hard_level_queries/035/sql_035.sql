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
        DATETIME_DIFF(adm.dischtime, adm.admittime, HOUR) / 24.0 AS los_days,
        CASE
            WHEN adm.next_admittime IS NOT NULL
                AND DATE_DIFF(DATE(adm.next_admittime), DATE(adm.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted
    FROM
        all_admissions_with_next AS adm
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON adm.hadm_id = d.hadm_id
    WHERE
        adm.gender = 'M'
        AND adm.insurance = 'Medicare'
        AND adm.age_at_admission BETWEEN 68 AND 78
        AND (
            UPPER(adm.admission_location) LIKE '%SKILLED NURSING%'
            OR UPPER(adm.admission_location) LIKE '%SNF%'
        )
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND (d.icd_code LIKE '5990%' OR d.icd_code LIKE '595%' OR d.icd_code LIKE '590%'))
            OR (d.icd_version = 10 AND (d.icd_code LIKE 'N390%' OR d.icd_code LIKE 'N30%' OR d.icd_code LIKE 'N10%'))
        )
        AND adm.dischtime IS NOT NULL
)
SELECT
    SAFE_DIVIDE(SUM(is_readmitted), COUNT(hadm_id)) * 100 AS readmission_rate_30_day_pct,
    APPROX_QUANTILES(IF(is_readmitted = 1, los_days, NULL), 100)[OFFSET(50)] AS median_los_readmitted_days,
    APPROX_QUANTILES(IF(is_readmitted = 0, los_days, NULL), 100)[OFFSET(50)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(COUNTIF(los_days > 6), COUNT(hadm_id)) * 100 AS pct_los_gt_6_days
FROM
    index_admissions;
