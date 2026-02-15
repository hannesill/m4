WITH
  cohort_base AS (
    SELECT
      a.hadm_id,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
        ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 72 AND 82
  ),
  hf_cohort AS (
    SELECT DISTINCT
      cb.hadm_id,
      cb.hospital_expire_flag,
      cb.los_days
    FROM
      cohort_base AS cb
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON cb.hadm_id = d.hadm_id
    WHERE
      (
        d.icd_code LIKE '428%'
        OR d.icd_code LIKE 'I50%'
      )
      AND cb.los_days IS NOT NULL AND cb.los_days >= 0
  ),
  comorbidity_counts AS (
    SELECT
      h.hadm_id,
      COUNT(DISTINCT d.icd_code) AS comorbidity_count
    FROM
      hf_cohort AS h
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON h.hadm_id = d.hadm_id
    GROUP BY
      h.hadm_id
  ),
  stratified_cohort AS (
    SELECT
      hf.hadm_id,
      hf.hospital_expire_flag,
      hf.los_days,
      cc.comorbidity_count,
      CASE
        WHEN icu.hadm_id IS NOT NULL
        THEN 'Higher-Severity (ICU)'
        ELSE 'Lower-Severity (Non-ICU)'
      END AS severity_group,
      CASE
        WHEN hf.los_days <= 3
        THEN '≤3 days'
        WHEN hf.los_days BETWEEN 4 AND 6
        THEN '4-6 days'
        WHEN hf.los_days BETWEEN 7 AND 10
        THEN '7-10 days'
        ELSE '>10 days'
      END AS los_bucket
    FROM
      hf_cohort AS hf
      LEFT JOIN (
        SELECT DISTINCT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_icu.icustays`
      ) AS icu
        ON hf.hadm_id = icu.hadm_id
      INNER JOIN comorbidity_counts AS cc
        ON hf.hadm_id = cc.hadm_id
  ),
  severity_levels AS (
    SELECT
      'Higher-Severity (ICU)' AS severity_group
    UNION ALL
    SELECT
      'Lower-Severity (Non-ICU)' AS severity_group
  ),
  los_levels AS (
    SELECT
      '≤3 days' AS los_bucket,
      1 AS sort_order
    UNION ALL
    SELECT
      '4-6 days' AS los_bucket,
      2 AS sort_order
    UNION ALL
    SELECT
      '7-10 days' AS los_bucket,
      3 AS sort_order
    UNION ALL
    SELECT
      '>10 days' AS los_bucket,
      4 AS sort_order
  ),
  strata_scaffold AS (
    SELECT
      *
    FROM
      severity_levels
      CROSS JOIN los_levels
  ),
  grouped_results AS (
    SELECT
      severity_group,
      los_bucket,
      COUNT(hadm_id) AS N,
      ROUND(AVG(hospital_expire_flag) * 100, 2) AS in_hospital_mortality_rate_pct,
      CAST(APPROX_QUANTILES(los_days, 100)[OFFSET(50)] AS INT64) AS median_los_days,
      ROUND(AVG(comorbidity_count), 1) AS average_comorbidity_count
    FROM
      stratified_cohort
    GROUP BY
      severity_group,
      los_bucket
  )
SELECT
  s.severity_group,
  s.los_bucket,
  COALESCE(g.N, 0) AS N,
  g.in_hospital_mortality_rate_pct,
  g.median_los_days,
  g.average_comorbidity_count
FROM
  strata_scaffold AS s
  LEFT JOIN grouped_results AS g
    ON s.severity_group = g.severity_group
    AND s.los_bucket = g.los_bucket
ORDER BY
  s.severity_group DESC,
  s.sort_order;
