WITH
  all_admissions_with_next AS (
    SELECT
      a.hadm_id,
      a.subject_id,
      a.admittime,
      a.dischtime,
      a.admission_location,
      a.insurance,
      p.gender,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days,
      LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      a.dischtime IS NOT NULL
  ),
  index_admissions AS (
    SELECT
      all_adm.hadm_id,
      all_adm.dischtime,
      all_adm.los_days,
      all_adm.next_admittime
    FROM
      all_admissions_with_next AS all_adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON all_adm.hadm_id = d.hadm_id
    WHERE
      all_adm.gender = 'F'
      AND all_adm.age_at_admission BETWEEN 43 AND 53
      AND all_adm.insurance = 'Medicare'
      AND UPPER(all_adm.admission_location) LIKE '%EMERGENCY%'
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '560%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'K56%')
      )
  ),
  index_admissions_with_readmission_flag AS (
    SELECT
      idx.hadm_id,
      idx.los_days,
      CASE
        WHEN
          idx.next_admittime IS NOT NULL
          AND DATE_DIFF(DATE(idx.next_admittime), DATE(idx.dischtime), DAY) <= 30
          THEN TRUE
        ELSE FALSE
      END AS is_readmitted_30_days
    FROM index_admissions AS idx
  )
SELECT
  'Female Medicare patients, aged 43-53, admitted via ED with principal diagnosis of bowel obstruction' AS cohort_description,
  COUNT(hadm_id) AS total_admissions,
  SAFE_DIVIDE(COUNTIF(is_readmitted_30_days), COUNT(hadm_id)) * 100.0 AS readmission_rate_30_day_pct,
  APPROX_QUANTILES(IF(is_readmitted_30_days, los_days, NULL), 2)[OFFSET(1)] AS median_los_readmitted_days,
  APPROX_QUANTILES(IF(NOT is_readmitted_30_days, los_days, NULL), 2)[OFFSET(1)] AS median_los_not_readmitted_days,
  SAFE_DIVIDE(COUNTIF(los_days > 7), COUNT(hadm_id)) * 100.0 AS pct_admissions_with_los_gt_7_days
FROM index_admissions_with_readmission_flag;
