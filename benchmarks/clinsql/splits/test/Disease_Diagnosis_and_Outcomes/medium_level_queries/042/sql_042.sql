WITH
  los_strata AS (
    SELECT
      '1-3 days' AS los_bucket,
      1 AS sort_order
    UNION ALL
    SELECT
      '4-7 days' AS los_bucket,
      2 AS sort_order
    UNION ALL
    SELECT
      '>=8 days' AS los_bucket,
      3 AS sort_order
  ),
  cohort AS (
    SELECT
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.discharge_location,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year
      ) BETWEEN 69 AND 79
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            (
              d.icd_version = 9
              AND d.icd_code LIKE '410%'
            )
            OR (
              d.icd_version = 10
              AND d.icd_code LIKE 'I21%'
            )
          )
      )
      AND NOT EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            (
              d.icd_version = 9
              AND d.icd_code LIKE '785.5%'
            )
            OR (
              d.icd_version = 10
              AND (
                d.icd_code LIKE 'R57.%'
                OR d.icd_code = 'R65.21'
              )
            )
            OR (
              d.icd_version = 9
              AND d.icd_code IN ('518.81', '518.82', '518.84')
            )
            OR (
              d.icd_version = 10
              AND d.icd_code LIKE 'J96.%'
            )
          )
      )
  ),
  metrics_per_admission AS (
    SELECT
      hadm_id,
      hospital_expire_flag,
      DATETIME_DIFF(dischtime, admittime, DAY) AS los_days,
      CASE
        WHEN DATETIME_DIFF(dischtime, admittime, DAY) BETWEEN 1 AND 3
        THEN '1-3 days'
        WHEN DATETIME_DIFF(dischtime, admittime, DAY) BETWEEN 4 AND 7
        THEN '4-7 days'
        WHEN DATETIME_DIFF(dischtime, admittime, DAY) >= 8
        THEN '>=8 days'
        ELSE NULL
      END AS los_bucket,
      CASE
        WHEN discharge_location IN ('HOME', 'HOME HEALTH CARE')
        THEN 'Home'
        WHEN discharge_location = 'REHAB/DISTINCT PART HOSP'
        THEN 'Rehab'
        WHEN discharge_location = 'SKILLED NURSING FACILITY'
        THEN 'SNF'
        WHEN discharge_location = 'HOSPICE'
        THEN 'Hospice'
        ELSE 'Other'
      END AS discharge_category
    FROM
      cohort
  ),
  aggregated_results AS (
    SELECT
      los_bucket,
      COUNT(hadm_id) AS N,
      AVG(hospital_expire_flag) AS avg_mortality,
      APPROX_QUANTILES(los_days, 2) [OFFSET (1)] AS median_los_days_val,
      COUNTIF(discharge_category = 'Home') AS discharge_home_count,
      COUNTIF(discharge_category = 'Rehab') AS discharge_rehab_count,
      COUNTIF(discharge_category = 'SNF') AS discharge_snf_count,
      COUNTIF(discharge_category = 'Hospice') AS discharge_hospice_count
    FROM
      metrics_per_admission
    WHERE
      los_bucket IS NOT NULL
    GROUP BY
      los_bucket
  )
SELECT
  s.los_bucket,
  COALESCE(ar.N, 0) AS N,
  ROUND(COALESCE(ar.avg_mortality, 0) * 100, 2) AS mortality_rate_pct,
  CAST(ar.median_los_days_val AS INT64) AS median_los_days,
  COALESCE(ar.discharge_home_count, 0) AS discharge_home_count,
  COALESCE(ar.discharge_rehab_count, 0) AS discharge_rehab_count,
  COALESCE(ar.discharge_snf_count, 0) AS discharge_snf_count,
  COALESCE(ar.discharge_hospice_count, 0) AS discharge_hospice_count,
  ROUND(
    SAFE_DIVIDE(COALESCE(ar.discharge_home_count, 0), ar.N) * 100,
    2
  ) AS discharge_home_pct,
  ROUND(
    SAFE_DIVIDE(COALESCE(ar.discharge_rehab_count, 0), ar.N) * 100,
    2
  ) AS discharge_rehab_pct,
  ROUND(
    SAFE_DIVIDE(COALESCE(ar.discharge_snf_count, 0), ar.N) * 100,
    2
  ) AS discharge_snf_pct,
  ROUND(
    SAFE_DIVIDE(COALESCE(ar.discharge_hospice_count, 0), ar.N) * 100,
    2
  ) AS discharge_hospice_pct
FROM
  los_strata AS s
  LEFT JOIN aggregated_results AS ar ON s.los_bucket = ar.los_bucket
ORDER BY
  s.sort_order;
