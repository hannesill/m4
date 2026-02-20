WITH
  index_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 77 AND 87
      AND a.insurance = 'Medicare'
      AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
      AND d.seq_num = 1
      AND (
        (d.icd_code LIKE '486%' AND d.icd_version = 9)
        OR (d.icd_code LIKE 'J18%' AND d.icd_version = 10)
      )
  ),
  subject_admission_sequence AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    WHERE a.subject_id IN (SELECT DISTINCT subject_id FROM index_admissions)
  ),
  cohort_with_metrics AS (
    SELECT
      idx.hadm_id,
      DATETIME_DIFF(seq.dischtime, seq.admittime, HOUR) / 24.0 AS los_days,
      CASE
        WHEN
          seq.next_admittime IS NOT NULL
          AND seq.next_admittime > seq.dischtime
          AND DATE_DIFF(DATE(seq.next_admittime), DATE(seq.dischtime), DAY) <= 30
          THEN 1
        ELSE 0
      END AS is_readmitted_30_days
    FROM index_admissions AS idx
    INNER JOIN subject_admission_sequence AS seq
      ON idx.hadm_id = seq.hadm_id
    WHERE
      seq.dischtime IS NOT NULL
  )
SELECT
  COUNT(*) AS total_cohort_admissions,
  SAFE_DIVIDE(SUM(is_readmitted_30_days), COUNT(*)) * 100.0 AS readmission_rate_30_day_percent,
  APPROX_QUANTILES(IF(is_readmitted_30_days = 0, los_days, NULL), 2)[OFFSET(1)] AS median_los_not_readmitted_days,
  APPROX_QUANTILES(IF(is_readmitted_30_days = 1, los_days, NULL), 2)[OFFSET(1)] AS median_los_readmitted_days,
  SAFE_DIVIDE(SUM(IF(los_days > 7, 1, 0)), COUNT(*)) * 100.0 AS percent_los_gt_7_days
FROM cohort_with_metrics;
