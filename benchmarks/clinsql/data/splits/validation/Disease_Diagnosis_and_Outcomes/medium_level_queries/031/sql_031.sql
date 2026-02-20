WITH
  sepsis_diagnoses AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 5) = '99591' THEN 1
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'A41' THEN 1
          ELSE 0
        END
      ) AS has_sepsis,
      MAX(
        CASE
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 5) = '78552' THEN 1
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 5) = 'R65.21' THEN 1
          ELSE 0
        END
      ) AS has_septic_shock
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  final_cohort AS (
    SELECT
      a.hadm_id,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days,
      CASE
        WHEN sd.has_septic_shock = 1 THEN 'Septic Shock'
        ELSE 'Sepsis'
      END AS sepsis_severity,
      CASE
        WHEN DATETIME_DIFF(a.dischtime, a.admittime, DAY) <= 7 THEN '≤7 days'
        ELSE '>7 days'
      END AS los_group
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN sepsis_diagnoses AS sd
      ON a.hadm_id = sd.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 53 AND 63
      AND (
        sd.has_sepsis = 1 OR sd.has_septic_shock = 1
      )
  )
SELECT
  fc.sepsis_severity,
  COUNTIF(fc.los_group = '≤7 days') AS N_los_le_7_days,
  ROUND(
    SAFE_DIVIDE(
      SUM(IF(fc.los_group = '≤7 days', fc.hospital_expire_flag, 0)),
      COUNTIF(fc.los_group = '≤7 days')
    ) * 100,
    2
  ) AS mortality_rate_los_le_7_days,
  CAST(APPROX_QUANTILES(
    IF(fc.los_group = '≤7 days' AND fc.hospital_expire_flag = 1, fc.los_days, NULL),
    2 IGNORE NULLS
  )[OFFSET(1)] AS INT64) AS median_time_to_death_los_le_7_days,
  COUNTIF(fc.los_group = '>7 days') AS N_los_gt_7_days,
  ROUND(
    SAFE_DIVIDE(
      SUM(IF(fc.los_group = '>7 days', fc.hospital_expire_flag, 0)),
      COUNTIF(fc.los_group = '>7 days')
    ) * 100,
    2
  ) AS mortality_rate_los_gt_7_days,
  CAST(APPROX_QUANTILES(
    IF(fc.los_group = '>7 days' AND fc.hospital_expire_flag = 1, fc.los_days, NULL),
    2 IGNORE NULLS
  )[OFFSET(1)] AS INT64) AS median_time_to_death_los_gt_7_days,
  ROUND(
    (
      SAFE_DIVIDE(
        SUM(IF(fc.los_group = '>7 days', fc.hospital_expire_flag, 0)),
        COUNTIF(fc.los_group = '>7 days')
      ) * 100
    ) - (
      SAFE_DIVIDE(
        SUM(IF(fc.los_group = '≤7 days', fc.hospital_expire_flag, 0)),
        COUNTIF(fc.los_group = '≤7 days')
      ) * 100
    ),
    2
  ) AS absolute_mortality_difference,
  ROUND(
    SAFE_DIVIDE(
      (
        SAFE_DIVIDE(SUM(IF(fc.los_group = '>7 days', fc.hospital_expire_flag, 0)), COUNTIF(fc.los_group = '>7 days'))
      ) - (
        SAFE_DIVIDE(SUM(IF(fc.los_group = '≤7 days', fc.hospital_expire_flag, 0)), COUNTIF(fc.los_group = '≤7 days'))
      ),
      (
        SAFE_DIVIDE(SUM(IF(fc.los_group = '≤7 days', fc.hospital_expire_flag, 0)), COUNTIF(fc.los_group = '≤7 days'))
      )
    ) * 100,
    2
  ) AS relative_mortality_difference_pct
FROM final_cohort AS fc
GROUP BY
  fc.sepsis_severity
ORDER BY
  fc.sepsis_severity;
