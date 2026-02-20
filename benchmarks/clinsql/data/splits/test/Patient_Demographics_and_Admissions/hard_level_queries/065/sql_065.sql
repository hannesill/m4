WITH
  index_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 72 AND 82
      AND UPPER(a.admission_location) LIKE '%TRANSFER%HOSP%'
      AND a.dischtime IS NOT NULL
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND d.icd_code = '4111')
        OR (d.icd_version = 10 AND d.icd_code = 'I200')
      )
  ),
  all_admissions_ranked AS (
    SELECT
      hadm_id,
      admittime,
      dischtime,
      LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  index_admissions_with_readmission AS (
    SELECT
      i.hadm_id,
      DATETIME_DIFF(i.dischtime, i.admittime, HOUR) / 24.0 AS los_days,
      CASE
        WHEN
          r.next_admittime IS NOT NULL
          AND DATE_DIFF(DATE(r.next_admittime), DATE(i.dischtime), DAY) BETWEEN 1 AND 30
          THEN 1
        ELSE 0
      END AS is_readmitted_30_days
    FROM
      index_admissions AS i
    INNER JOIN
      all_admissions_ranked AS r
      ON i.hadm_id = r.hadm_id
  )
SELECT
  COUNT(hadm_id) AS total_admissions,
  SAFE_DIVIDE(SUM(is_readmitted_30_days) * 100.0, COUNT(hadm_id)) AS readmission_rate_30_day_pct,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_non_readmitted_days,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_readmitted_days,
  SAFE_DIVIDE(COUNTIF(los_days > 7) * 100.0, COUNT(hadm_id)) AS pct_los_gt_7_days
FROM
  index_admissions_with_readmission;
