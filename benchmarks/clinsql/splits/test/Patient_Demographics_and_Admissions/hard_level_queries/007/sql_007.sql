WITH index_admissions AS (
    SELECT
        a.subject_id,
        a.hadm_id,
        a.admittime,
        a.dischtime,
        DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
        p.gender = 'M'
        AND a.insurance = 'Medicare'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 83 AND 93
        AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
        AND d.seq_num = 1
        AND (
            (d.icd_version = 9 AND d.icd_code LIKE '435%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'G45%')
        )
        AND a.dischtime IS NOT NULL
),
all_subject_admissions AS (
    SELECT
        subject_id,
        hadm_id,
        admittime,
        dischtime,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM
        `physionet-data.mimiciv_3_1_hosp.admissions`
    WHERE
        subject_id IN (SELECT DISTINCT subject_id FROM index_admissions)
),
readmission_flags AS (
    SELECT
        ia.hadm_id,
        ia.los_days,
        CASE
            WHEN asa.next_admittime IS NOT NULL
                AND asa.next_admittime > ia.dischtime
                AND DATE_DIFF(DATE(asa.next_admittime), DATE(ia.dischtime), DAY) <= 30
            THEN 1
            ELSE 0
        END AS is_readmitted
    FROM
        index_admissions AS ia
    LEFT JOIN
        all_subject_admissions AS asa
        ON ia.hadm_id = asa.hadm_id
)
SELECT
    SAFE_DIVIDE(SUM(is_readmitted), COUNT(*)) * 100.0 AS readmission_rate_30_day_percent,
    APPROX_QUANTILES(CASE WHEN is_readmitted = 1 THEN los_days END, 2)[OFFSET(1)] AS median_los_readmitted_days,
    APPROX_QUANTILES(CASE WHEN is_readmitted = 0 THEN los_days END, 2)[OFFSET(1)] AS median_los_not_readmitted_days,
    SAFE_DIVIDE(COUNTIF(los_days > 10), COUNT(*)) * 100.0 AS percent_los_gt_10_days
FROM
    readmission_flags;
