WITH
index_admissions AS (
  SELECT
    a.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
    AND a.insurance = 'Medicare'
    AND (
      UPPER(a.admission_location) LIKE '%SKILLED NURSING%'
      OR UPPER(a.admission_location) LIKE '%SNF%'
    )
    AND d.seq_num = 1
    AND (
      (d.icd_version = 9 AND d.icd_code = '51881')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'J960%')
    )
    AND a.dischtime IS NOT NULL
),
admission_sequences AS (
  SELECT
    a.hadm_id,
    LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  WHERE a.subject_id IN (SELECT DISTINCT subject_id FROM index_admissions)
),
readmission_info AS (
  SELECT
    idx.hadm_id,
    idx.los_days,
    CASE
      WHEN seq.next_admittime IS NOT NULL
        AND DATE_DIFF(DATE(seq.next_admittime), DATE(idx.dischtime), DAY) <= 30
      THEN 1
      ELSE 0
    END AS is_readmitted_30_days
  FROM index_admissions AS idx
  LEFT JOIN admission_sequences AS seq
    ON idx.hadm_id = seq.hadm_id
)
SELECT
  SAFE_DIVIDE(SUM(is_readmitted_30_days), COUNT(*)) * 100 AS readmission_rate_30_day_pct,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_readmitted,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_not_readmitted,
  SAFE_DIVIDE(
    SUM(CASE WHEN los_days > 8 THEN 1 ELSE 0 END),
    COUNT(*)
  ) * 100 AS pct_los_gt_8_days
FROM readmission_info;
