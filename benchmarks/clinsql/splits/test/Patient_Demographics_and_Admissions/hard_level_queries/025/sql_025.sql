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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 65 AND 75
      AND a.insurance = 'Medicare'
      AND UPPER(a.admission_location) LIKE '%TRANSFER%HOSP%'
      AND a.dischtime IS NOT NULL
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '428%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
      )
  ),
  all_subject_admissions AS (
    SELECT
      adm.hadm_id,
      adm.dischtime,
      LEAD(adm.admittime, 1) OVER (PARTITION BY adm.subject_id ORDER BY adm.admittime)
        AS next_admittime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    WHERE adm.subject_id IN (SELECT DISTINCT subject_id FROM index_admissions)
  ),
  cohort_with_readmission AS (
    SELECT
      ia.hadm_id,
      ia.los_days,
      CASE
        WHEN
          asa.next_admittime IS NOT NULL
          AND asa.next_admittime > ia.dischtime
          AND DATE_DIFF(DATE(asa.next_admittime), DATE(ia.dischtime), DAY) <= 30
          THEN 1
        ELSE 0
      END AS is_readmitted_30_days
    FROM index_admissions AS ia
    INNER JOIN all_subject_admissions AS asa
      ON ia.hadm_id = asa.hadm_id
  )
SELECT
  COUNT(hadm_id) AS total_cohort_admissions,
  AVG(is_readmitted_30_days) * 100.0 AS readmission_rate_30_day_pct,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 1 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_days_readmitted,
  APPROX_QUANTILES(
    CASE WHEN is_readmitted_30_days = 0 THEN los_days END, 2
  )[OFFSET(1)] AS median_los_days_not_readmitted,
  AVG(CASE WHEN los_days > 7.0 THEN 1.0 ELSE 0.0 END) * 100.0 AS pct_los_gt_7_days
FROM cohort_with_readmission;
