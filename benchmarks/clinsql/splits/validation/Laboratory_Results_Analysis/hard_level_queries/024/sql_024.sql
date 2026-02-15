WITH
  target_cohort_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 53 AND 63
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE
          dx.hadm_id = a.hadm_id
          AND (dx.icd_code = '4275' OR dx.icd_code LIKE 'I46%')
      )
  ),
  critical_labs_first_48h AS (
    SELECT
      le.hadm_id,
      CASE
        WHEN le.itemid IN (50983, 50824) AND (le.valuenum < 125 OR le.valuenum > 155) THEN 1
        WHEN le.itemid IN (50971, 50822) AND (le.valuenum < 2.5 OR le.valuenum > 6.0) THEN 1
        WHEN le.itemid = 50912 AND le.valuenum > 4.0 THEN 1
        WHEN le.itemid = 50813 AND le.valuenum > 4.0 THEN 1
        WHEN le.itemid IN (51300, 51301) AND (le.valuenum < 2.0 OR le.valuenum > 20.0) THEN 1
        WHEN le.itemid = 51265 AND le.valuenum < 50 THEN 1
        WHEN le.itemid = 50820 AND (le.valuenum < 7.20 OR le.valuenum > 7.60) THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON le.hadm_id = a.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND DATETIME_DIFF(le.charttime, a.admittime, HOUR) BETWEEN 0 AND 48
      AND le.itemid IN (
        50983, 50824,
        50971, 50822,
        50912,
        50813,
        51300, 51301,
        51265,
        50820
      )
  ),
  cohort_instability_scores AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      c.los_days,
      COALESCE(SUM(l.is_critical), 0) AS instability_score
    FROM
      target_cohort_admissions AS c
    LEFT JOIN
      critical_labs_first_48h AS l
      ON c.hadm_id = l.hadm_id
    GROUP BY
      c.hadm_id, c.hospital_expire_flag, c.los_days
  ),
  cohort_percentile_value AS (
    SELECT
      PERCENTILE_CONT(instability_score, 0.9) OVER() AS p90_instability_score
    FROM
      cohort_instability_scores
    LIMIT 1
  ),
  top_tier_cohort AS (
    SELECT
      s.hadm_id,
      s.hospital_expire_flag,
      s.los_days
    FROM
      cohort_instability_scores AS s,
      cohort_percentile_value AS p
    WHERE
      s.instability_score >= p.p90_instability_score
  ),
  top_tier_outcomes AS (
    SELECT
      COUNT(*) AS top_tier_patient_count,
      AVG(hospital_expire_flag) AS top_tier_mortality_rate,
      AVG(los_days) AS top_tier_avg_los
    FROM
      top_tier_cohort
  ),
  critical_lab_rates AS (
    SELECT
      SAFE_DIVIDE(
        SUM(IF(l.hadm_id IN (SELECT hadm_id FROM top_tier_cohort), l.is_critical, 0)),
        COUNTIF(l.hadm_id IN (SELECT hadm_id FROM top_tier_cohort))
      ) AS top_tier_critical_lab_frequency,
      SAFE_DIVIDE(SUM(l.is_critical), COUNT(*)) AS general_pop_critical_lab_frequency
    FROM
      critical_labs_first_48h AS l
  )
SELECT
  p.p90_instability_score,
  o.top_tier_patient_count,
  o.top_tier_mortality_rate,
  o.top_tier_avg_los,
  r.top_tier_critical_lab_frequency,
  r.general_pop_critical_lab_frequency
FROM
  cohort_percentile_value AS p,
  top_tier_outcomes AS o,
  critical_lab_rates AS r;
