WITH
  ami_cohort_base AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 44 AND 54
      AND (
        (d.icd_code LIKE '410%' AND d.icd_version = 9)
        OR (d.icd_code LIKE 'I21%' AND d.icd_version = 10)
      )
  ),
  all_lab_events_with_criticality AS (
    SELECT
      lab.hadm_id,
      lab.charttime,
      CASE
        WHEN lab.itemid IN (50971, 50822) AND (lab.valuenum < 2.5 OR lab.valuenum > 6.5) THEN 1
        WHEN lab.itemid IN (50983, 50824) AND (lab.valuenum < 120 OR lab.valuenum > 160) THEN 1
        WHEN lab.itemid IN (50912) AND lab.valuenum > 4.0 THEN 1
        WHEN lab.itemid IN (50813) AND lab.valuenum > 4.0 THEN 1
        WHEN lab.itemid IN (51301, 51300) AND (lab.valuenum < 2.0 OR lab.valuenum > 30.0) THEN 1
        WHEN lab.itemid IN (51265) AND lab.valuenum < 20 THEN 1
        WHEN lab.itemid IN (50820) AND (lab.valuenum < 7.20 OR lab.valuenum > 7.60) THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS lab
    WHERE
      lab.valuenum IS NOT NULL
      AND lab.hadm_id IS NOT NULL
      AND lab.itemid IN (
        50971, 50822,
        50983, 50824,
        50912,
        50813,
        51301, 51300,
        51265,
        50820
      )
  ),
  ami_cohort_labs_72h AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
      l.is_critical
    FROM
      ami_cohort_base AS c
    INNER JOIN
      all_lab_events_with_criticality AS l
      ON c.hadm_id = l.hadm_id
    WHERE
      l.charttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 72 HOUR)
  ),
  general_population_labs_72h AS (
    SELECT
      l.is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      all_lab_events_with_criticality AS l
      ON a.hadm_id = l.hadm_id
    WHERE
      l.charttime BETWEEN a.admittime AND DATETIME_ADD(a.admittime, INTERVAL 72 HOUR)
  ),
  ami_cohort_scores AS (
    SELECT
      hadm_id,
      MAX(hospital_expire_flag) AS hospital_expire_flag,
      MAX(los_days) AS los_days,
      SUM(is_critical) AS instability_score
    FROM
      ami_cohort_labs_72h
    GROUP BY
      hadm_id
  ),
  ami_cohort_summary AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(75)] AS p75_instability_score,
      AVG(los_days) AS avg_los_days,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent
    FROM
      ami_cohort_scores
  ),
  frequency_comparison AS (
    SELECT
      SAFE_DIVIDE(
        (SELECT SUM(is_critical) FROM ami_cohort_labs_72h),
        (SELECT COUNT(*) FROM ami_cohort_labs_72h)
      ) * 100 AS ami_cohort_critical_frequency_percent,
      SAFE_DIVIDE(
        (SELECT SUM(is_critical) FROM general_population_labs_72h),
        (SELECT COUNT(*) FROM general_population_labs_72h)
      ) * 100 AS general_population_critical_frequency_percent
  )
SELECT
  ROUND(acs.p75_instability_score, 2) AS p75_instability_score_ami_cohort,
  ROUND(acs.avg_los_days, 2) AS avg_los_days_ami_cohort,
  ROUND(acs.mortality_rate_percent, 2) AS mortality_rate_percent_ami_cohort,
  ROUND(fc.ami_cohort_critical_frequency_percent, 2) AS ami_cohort_critical_frequency_percent,
  ROUND(fc.general_population_critical_frequency_percent, 2) AS general_population_critical_frequency_percent
FROM
  ami_cohort_summary AS acs,
  frequency_comparison AS fc;
