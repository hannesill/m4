WITH
  base_admissions AS (
    SELECT
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 57 AND 67
  ),
  sepsis_diagnoses AS (
    SELECT
      b.hadm_id,
      b.admittime,
      b.dischtime,
      b.hospital_expire_flag,
      MAX(
        CASE
          WHEN d.icd_version = 9 AND d.icd_code = '78552' THEN 1
          WHEN d.icd_version = 10 AND d.icd_code = 'R6521' THEN 1
          ELSE 0
        END
      ) AS has_septic_shock,
      MAX(
        CASE
          WHEN d.icd_version = 9 AND d.icd_code = '99591' THEN 1
          WHEN d.icd_version = 10 AND STARTS_WITH(d.icd_code, 'A41') THEN 1
          ELSE 0
        END
      ) AS has_sepsis
    FROM
      base_admissions AS b
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON b.hadm_id = d.hadm_id
    GROUP BY
      b.hadm_id,
      b.admittime,
      b.dischtime,
      b.hospital_expire_flag
  ),
  cohort_stratified AS (
    SELECT
      s.hadm_id,
      s.hospital_expire_flag,
      CASE
        WHEN s.has_septic_shock = 1 THEN 'Septic Shock'
        ELSE 'Sepsis (without shock)'
      END AS sepsis_severity,
      CASE
        WHEN DATETIME_DIFF(s.dischtime, s.admittime, DAY) <= 7 THEN '≤7 days'
        ELSE '>7 days'
      END AS los_group,
      CASE
        WHEN c.charlson_comorbidity_index <= 3 THEN '≤3'
        WHEN c.charlson_comorbidity_index BETWEEN 4 AND 5 THEN '4–5'
        WHEN c.charlson_comorbidity_index > 5 THEN '>5'
        ELSE 'Unknown'
      END AS charlson_group
    FROM
      sepsis_diagnoses AS s
    INNER JOIN
      `physionet-data.mimiciv_3_1_derived.charlson` AS c
      ON s.hadm_id = c.hadm_id
    WHERE
      s.has_sepsis = 1 OR s.has_septic_shock = 1
  ),
  strata_scaffold AS (
    SELECT
      sepsis_severity,
      charlson_group
    FROM
      (
        SELECT
          sepsis_severity
        FROM
          UNNEST(['Sepsis (without shock)', 'Septic Shock']) AS sepsis_severity
      )
      CROSS JOIN (
        SELECT
          charlson_group
        FROM
          UNNEST(['≤3', '4–5', '>5']) AS charlson_group
      )
  )
SELECT
  scaffold.sepsis_severity,
  scaffold.charlson_group,
  COALESCE(COUNTIF(cohort.los_group = '≤7 days'), 0) AS n_admissions_le_7_days,
  ROUND(
    SAFE_DIVIDE(
      SUM(IF(cohort.los_group = '≤7 days', cohort.hospital_expire_flag, 0)),
      COUNTIF(cohort.los_group = '≤7 days')
    ) * 100,
    2
  ) AS mortality_rate_le_7_days,
  COALESCE(COUNTIF(cohort.los_group = '>7 days'), 0) AS n_admissions_gt_7_days,
  ROUND(
    SAFE_DIVIDE(
      SUM(IF(cohort.los_group = '>7 days', cohort.hospital_expire_flag, 0)),
      COUNTIF(cohort.los_group = '>7 days')
    ) * 100,
    2
  ) AS mortality_rate_gt_7_days,
  (
    ROUND(
      SAFE_DIVIDE(
        SUM(IF(cohort.los_group = '>7 days', cohort.hospital_expire_flag, 0)),
        COUNTIF(cohort.los_group = '>7 days')
      ) * 100,
      2
    )
  ) - (
    ROUND(
      SAFE_DIVIDE(
        SUM(IF(cohort.los_group = '≤7 days', cohort.hospital_expire_flag, 0)),
        COUNTIF(cohort.los_group = '≤7 days')
      ) * 100,
      2
    )
  ) AS absolute_mortality_difference,
  SAFE_DIVIDE(
    (
      ROUND(
        SAFE_DIVIDE(
          SUM(IF(cohort.los_group = '>7 days', cohort.hospital_expire_flag, 0)),
          COUNTIF(cohort.los_group = '>7 days')
        ) * 100,
        2
      )
    ),
    (
      ROUND(
        SAFE_DIVIDE(
          SUM(IF(cohort.los_group = '≤7 days', cohort.hospital_expire_flag, 0)),
          COUNTIF(cohort.los_group = '≤7 days')
        ) * 100,
        2
      )
    )
  ) AS relative_mortality_difference
FROM
  strata_scaffold AS scaffold
LEFT JOIN
  cohort_stratified AS cohort
  ON scaffold.sepsis_severity = cohort.sepsis_severity
  AND scaffold.charlson_group = cohort.charlson_group
GROUP BY
  scaffold.sepsis_severity,
  scaffold.charlson_group
ORDER BY
  scaffold.sepsis_severity,
  CASE
    WHEN scaffold.charlson_group = '≤3' THEN 1
    WHEN scaffold.charlson_group = '4–5' THEN 2
    WHEN scaffold.charlson_group = '>5' THEN 3
  END;
