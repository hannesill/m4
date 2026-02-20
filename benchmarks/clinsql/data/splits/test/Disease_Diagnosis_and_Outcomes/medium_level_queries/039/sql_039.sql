WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.admission_type,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year
      ) BETWEEN 66 AND 76
  ),
  ami_admissions AS (
    SELECT
      b.*
    FROM
      base_admissions AS b
    WHERE
      EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = b.hadm_id
          AND (
            d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) = '410'
            OR d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) = 'I21'
          )
      )
  ),
  final_cohort AS (
    SELECT
      ami.hadm_id,
      ami.hospital_expire_flag,
      DATETIME_DIFF(ami.dischtime, ami.admittime, DAY) AS hospital_los_days,
      CASE
        WHEN DATETIME_DIFF(ami.dischtime, ami.admittime, DAY) BETWEEN 1 AND 3
          THEN '1-3 days'
        WHEN DATETIME_DIFF(ami.dischtime, ami.admittime, DAY) BETWEEN 4 AND 7
          THEN '4-7 days'
        WHEN DATETIME_DIFF(ami.dischtime, ami.admittime, DAY) >= 8
          THEN '>=8 days'
        ELSE NULL
      END AS los_bucket,
      CASE
        WHEN ami.admission_type IN ('EMERGENCY', 'URGENT', 'DIRECT EMER.', 'EW EMER.')
          THEN 'Emergent'
        ELSE 'Non-Emergent'
      END AS admission_type_group
    FROM
      ami_admissions AS ami
    WHERE
      NOT EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = ami.hadm_id
          AND (
            (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 4) = '7855')
            OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('R57', 'R65'))
            OR (d.icd_version = 9 AND d.icd_code IN ('51881', '51882', '51884', '7991'))
            OR (d.icd_version = 10 AND (SUBSTR(d.icd_code, 1, 3) = 'J96' OR d.icd_code = 'R092'))
          )
      )
  ),
  strata_grid AS (
    SELECT
      los_bucket,
      admission_type_group,
      los_bucket_order
    FROM
      (
        SELECT '1-3 days' AS los_bucket, 1 AS los_bucket_order UNION ALL
        SELECT '4-7 days' AS los_bucket, 2 AS los_bucket_order UNION ALL
        SELECT '>=8 days' AS los_bucket, 3 AS los_bucket_order
      )
      CROSS JOIN
      (
        SELECT 'Emergent' AS admission_type_group UNION ALL
        SELECT 'Non-Emergent' AS admission_type_group
      )
  ),
  grouped_stats AS (
    SELECT
      los_bucket,
      admission_type_group,
      COUNT(hadm_id) AS number_of_admissions,
      ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
      CAST(APPROX_QUANTILES(
        CASE WHEN hospital_expire_flag = 1 THEN hospital_los_days END, 2
      )[OFFSET(1)] AS INT64) AS median_time_to_death_days
    FROM
      final_cohort
    WHERE
      los_bucket IS NOT NULL
    GROUP BY
      los_bucket,
      admission_type_group
  )
SELECT
  s.admission_type_group,
  s.los_bucket,
  COALESCE(g.number_of_admissions, 0) AS number_of_admissions,
  g.mortality_rate_pct,
  g.median_time_to_death_days
FROM
  strata_grid AS s
  LEFT JOIN grouped_stats AS g
    ON s.los_bucket = g.los_bucket AND s.admission_type_group = g.admission_type_group
ORDER BY
  s.admission_type_group DESC,
  s.los_bucket_order;
