WITH
  index_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 80 AND 90
      AND a.insurance = 'Medicare'
      AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '730%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'M86%')
      )
      AND a.dischtime IS NOT NULL
  ),
  admission_sequences AS (
    SELECT
      subject_id,
      hadm_id,
      admittime,
      LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  cohort_with_metrics AS (
    SELECT
      idx.hadm_id,
      DATETIME_DIFF(idx.dischtime, idx.admittime, HOUR) / 24.0 AS los_days,
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
  COUNT(hadm_id) AS total_cohort_admissions,
  SAFE_DIVIDE(SUM(is_readmitted_30_days) * 100.0, COUNT(hadm_id)) AS readmission_rate_30_day_percent,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_readmitted_days,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_not_readmitted_days,
  SAFE_DIVIDE(COUNTIF(los_days > 7) * 100.0, COUNT(hadm_id)) AS percent_los_gt_7_days
FROM cohort_with_metrics;
