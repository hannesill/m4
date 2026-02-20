WITH
  all_subject_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.admission_location,
      a.insurance,
      p.gender,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, HOUR) / 24.0 AS los_days,
      LEAD(a.admittime, 1) OVER (
        PARTITION BY
          a.subject_id
        ORDER BY
          a.admittime
      ) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      a.dischtime IS NOT NULL
  ),
  index_admissions AS (
    SELECT
      aa.hadm_id,
      aa.los_days,
      CASE
        WHEN aa.next_admittime IS NOT NULL AND DATE_DIFF(DATE(aa.next_admittime), DATE(aa.dischtime), DAY) <= 30 THEN 1
        ELSE 0
      END AS is_readmitted_30_days
    FROM
      all_subject_admissions AS aa
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON aa.hadm_id = d.hadm_id
    WHERE
      aa.gender = 'F'
      AND aa.insurance = 'Medicare'
      AND aa.age_at_admission BETWEEN 58 AND 68
      AND UPPER(aa.admission_location) LIKE '%EMERGENCY%'
      AND d.seq_num = 1
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '820%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'S720%')
      )
  )
SELECT
  AVG(ia.is_readmitted_30_days) * 100 AS readmission_rate_30_day_percent,
  APPROX_QUANTILES(
    IF(ia.is_readmitted_30_days = 1, ia.los_days, NULL), 100
  )[OFFSET(50)] AS median_los_readmitted_days,
  APPROX_QUANTILES(
    IF(ia.is_readmitted_30_days = 0, ia.los_days, NULL), 100
  )[OFFSET(50)] AS median_los_non_readmitted_days,
  AVG(IF(ia.los_days > 8, 1, 0)) * 100 AS percent_los_gt_8_days
FROM
  index_admissions AS ia;
