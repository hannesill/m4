WITH
  all_admissions_with_next AS (
    SELECT
      p.subject_id,
      p.gender,
      p.anchor_age,
      p.anchor_year,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.admission_type,
      a.admission_location,
      a.insurance,
      a.hospital_expire_flag,
      LEAD(a.admittime, 1) OVER (
        PARTITION BY
          p.subject_id
        ORDER BY
          a.admittime
      ) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  ),
  index_admissions AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.next_admittime,
      (adm.anchor_age + EXTRACT(YEAR FROM adm.admittime) - adm.anchor_year) AS age_at_admission,
      DATETIME_DIFF(adm.dischtime, adm.admittime, HOUR) / 24.0 AS los_days,
      CASE
        WHEN adm.dischtime IS NOT NULL AND adm.next_admittime IS NOT NULL AND DATE_DIFF(DATE(adm.next_admittime), DATE(adm.dischtime), DAY) <= 30 THEN 1
        ELSE 0
      END AS is_readmitted_30_days
    FROM
      all_admissions_with_next AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON adm.hadm_id = d.hadm_id
    WHERE
      adm.gender = 'F'
      AND (adm.anchor_age + EXTRACT(YEAR FROM adm.admittime) - adm.anchor_year) BETWEEN 82 AND 92
      AND adm.insurance = 'Medicare'
      AND UPPER(adm.admission_location) LIKE '%EMERGENCY%'
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND d.icd_code = '5770')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'K85%')
      )
      AND adm.dischtime IS NOT NULL
  )
SELECT
  COUNT(hadm_id) AS total_admissions,
  SAFE_DIVIDE(SUM(is_readmitted_30_days) * 100.0, COUNT(hadm_id)) AS readmission_rate_30_day_pct,
  APPROX_QUANTILES(
    CASE
      WHEN is_readmitted_30_days = 1 THEN los_days
    END,
    2
  )[OFFSET(1)] AS median_los_readmitted_days,
  APPROX_QUANTILES(
    CASE
      WHEN is_readmitted_30_days = 0 THEN los_days
    END,
    2
  )[OFFSET(1)] AS median_los_not_readmitted_days,
  SAFE_DIVIDE(COUNTIF(los_days > 7) * 100.0, COUNT(hadm_id)) AS pct_admissions_los_gt_7_days
FROM
  index_admissions;
