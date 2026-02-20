WITH
  index_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 55 AND 65
      AND a.insurance = 'Medicare'
      AND UPPER(a.admission_location) LIKE '%EMERGENCY%'
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND (d.icd_code LIKE '681%' OR d.icd_code LIKE '682%'))
        OR (d.icd_version = 10 AND d.icd_code LIKE 'L03%')
      )
  ),
  all_admissions_with_next AS (
    SELECT
      hadm_id,
      dischtime,
      LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
    WHERE
      subject_id IN (SELECT DISTINCT subject_id FROM index_admissions)
  ),
  readmission_cohort AS (
    SELECT
      ia.hadm_id,
      DATETIME_DIFF(ia.dischtime, ia.admittime, HOUR) / 24.0 AS los_days,
      CASE
        WHEN
          an.next_admittime IS NOT NULL
          AND an.next_admittime > ia.dischtime
          AND DATE_DIFF(DATE(an.next_admittime), DATE(ia.dischtime), DAY) <= 30
          THEN 1
        ELSE 0
      END AS is_readmitted
    FROM index_admissions AS ia
    INNER JOIN all_admissions_with_next AS an
      ON ia.hadm_id = an.hadm_id
    WHERE
      ia.dischtime IS NOT NULL
  )
SELECT
  SAFE_DIVIDE(SUM(is_readmitted), COUNT(*)) * 100.0 AS readmission_rate_30_day_pct,
  APPROX_QUANTILES(IF(is_readmitted = 1, los_days, NULL), 2)[OFFSET(1)] AS median_los_readmitted_days,
  APPROX_QUANTILES(IF(is_readmitted = 0, los_days, NULL), 2)[OFFSET(1)] AS median_los_not_readmitted_days,
  SAFE_DIVIDE(COUNTIF(los_days > 7), COUNT(*)) * 100.0 AS pct_index_los_gt_7_days
FROM readmission_cohort;
