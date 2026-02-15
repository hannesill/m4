WITH
  dvt_cohort AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 42 AND 52
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '4534%')
        OR (d.icd_version = 10 AND d.icd_code LIKE 'I824%')
      )
  ),
  all_labs_72h AS (
    SELECT
      le.hadm_id,
      le.itemid,
      le.valuenum,
      CASE WHEN dc.hadm_id IS NOT NULL THEN 1 ELSE 0 END AS is_dvt_cohort
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
      LEFT JOIN dvt_cohort AS dc ON le.hadm_id = dc.hadm_id
    WHERE
      le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 72 HOUR)
      AND le.valuenum IS NOT NULL
      AND le.itemid IN (
        50912,
        51003,
        50983,
        50971,
        50931,
        51006
      )
  ),
  labs_with_weighted_criticality AS (
    SELECT
      hadm_id,
      is_dvt_cohort,
      CASE
        WHEN itemid = 50983 AND (valuenum < 120 OR valuenum > 160) THEN 3
        WHEN itemid = 50971 AND (valuenum < 2.5 OR valuenum > 6.5) THEN 3
        WHEN itemid = 50912 AND valuenum > 4.0 THEN 2
        WHEN itemid = 51003 AND valuenum > 0.1 THEN 2
        WHEN itemid = 51006 AND valuenum > 100 THEN 1
        WHEN itemid = 50931 AND (valuenum < 40 OR valuenum > 500) THEN 1
        ELSE 0
      END AS criticality_weight
    FROM
      all_labs_72h
  ),
  cohort_instability_scores AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      c.los_days,
      COALESCE(SUM(l.criticality_weight), 0) AS instability_score
    FROM
      dvt_cohort AS c
      LEFT JOIN labs_with_weighted_criticality AS l ON c.hadm_id = l.hadm_id
    GROUP BY
      c.hadm_id,
      c.hospital_expire_flag,
      c.los_days
  ),
  cohort_percentiles AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(95)] AS p95_instability_score
    FROM
      cohort_instability_scores
  ),
  top_tier_outcomes AS (
    SELECT
      AVG(CAST(s.hospital_expire_flag AS FLOAT64)) AS top_tier_mortality_rate,
      AVG(s.los_days) AS top_tier_avg_los
    FROM
      cohort_instability_scores AS s
      CROSS JOIN cohort_percentiles AS p
    WHERE
      s.instability_score >= p.p95_instability_score
      AND p.p95_instability_score > 0
  ),
  comparative_rates AS (
    SELECT
      SAFE_DIVIDE(
        SUM(CASE WHEN is_dvt_cohort = 1 AND criticality_weight > 0 THEN 1 ELSE 0 END),
        COUNTIF(is_dvt_cohort = 1)
      ) AS target_cohort_critical_lab_rate,
      SAFE_DIVIDE(SUM(CASE WHEN criticality_weight > 0 THEN 1 ELSE 0 END), COUNT(*)) AS general_population_critical_lab_rate
    FROM
      labs_with_weighted_criticality
  )
SELECT
  'Male inpatients aged 42-52 with DVT' AS target_cohort_description,
  p.p95_instability_score,
  t.top_tier_mortality_rate,
  t.top_tier_avg_los,
  c.target_cohort_critical_lab_rate,
  c.general_population_critical_lab_rate
FROM
  cohort_percentiles AS p,
  top_tier_outcomes AS t,
  comparative_rates AS c;
