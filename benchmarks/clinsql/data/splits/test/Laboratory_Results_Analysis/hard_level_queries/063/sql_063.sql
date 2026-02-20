WITH
  pe_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (
        EXTRACT(
          YEAR
          FROM a.admittime
        ) - p.anchor_year
      ) + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (
        (
          EXTRACT(
            YEAR
            FROM a.admittime
          ) - p.anchor_year
        ) + p.anchor_age
      ) BETWEEN 53 AND 63
      AND a.hadm_id IN (
        SELECT DISTINCT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          (
            icd_version = 9
            AND SUBSTR(icd_code, 1, 4) IN ('4151')
          )
          OR (
            icd_version = 10
            AND SUBSTR(icd_code, 1, 3) IN ('I26')
          )
      )
  ),
  critical_labs AS (
    SELECT
      hadm_id,
      charttime,
      itemid,
      valuenum,
      CASE
        WHEN itemid = 50983 AND (valuenum < 120 OR valuenum > 160) THEN 1
        WHEN itemid = 50971 AND (valuenum < 2.5 OR valuenum > 6.5) THEN 1
        WHEN itemid = 50912 AND valuenum > 4.0 THEN 1
        WHEN itemid = 50882 AND (valuenum < 10 OR valuenum > 40) THEN 1
        WHEN itemid = 51301 AND (valuenum < 1.0 OR valuenum > 50.0) THEN 1
        WHEN itemid = 51265 AND valuenum < 20 THEN 1
        WHEN itemid = 51222 AND valuenum < 7.0 THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents`
    WHERE
      hadm_id IS NOT NULL
      AND valuenum IS NOT NULL
      AND itemid IN (
        50983,
        50971,
        50912,
        50882,
        51301,
        51265,
        51222
      )
  ),
  pe_cohort_instability AS (
    SELECT
      pe.hadm_id,
      pe.hospital_expire_flag,
      DATETIME_DIFF(pe.dischtime, pe.admittime, DAY) AS los_days,
      SUM(cl.is_critical) AS instability_score,
      COUNT(cl.itemid) AS total_labs_in_window
    FROM
      pe_admissions AS pe
      INNER JOIN critical_labs AS cl ON pe.hadm_id = cl.hadm_id
    WHERE
      cl.charttime BETWEEN pe.admittime AND DATETIME_ADD(pe.admittime, INTERVAL 72 HOUR)
    GROUP BY
      pe.hadm_id,
      pe.hospital_expire_flag,
      los_days
  ),
  pe_cohort_percentiles AS (
    SELECT
      hadm_id,
      hospital_expire_flag,
      los_days,
      instability_score,
      total_labs_in_window,
      PERCENTILE_CONT(instability_score, 0.75) OVER () AS p75_instability_score
    FROM
      pe_cohort_instability
  ),
  top_tier_outcomes AS (
    SELECT
      MIN(p75_instability_score) AS p75_instability_score,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS top_tier_avg_mortality,
      AVG(los_days) AS top_tier_avg_los_days,
      SUM(instability_score) AS total_critical_labs_top_tier,
      SUM(total_labs_in_window) AS total_labs_measured_top_tier
    FROM
      pe_cohort_percentiles
    WHERE
      instability_score >= p75_instability_score
  ),
  general_population_stats AS (
    SELECT
      SUM(cl.is_critical) AS total_critical_labs_general_pop,
      COUNT(cl.itemid) AS total_labs_measured_general_pop
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN critical_labs AS cl ON a.hadm_id = cl.hadm_id
    WHERE
      cl.charttime BETWEEN a.admittime AND DATETIME_ADD(a.admittime, INTERVAL 72 HOUR)
  )
SELECT
  ROUND(tto.p75_instability_score, 2) AS p75_instability_score_pe_cohort,
  ROUND(tto.top_tier_avg_mortality * 100, 2) AS top_tier_pe_cohort_mortality_pct,
  ROUND(tto.top_tier_avg_los_days, 1) AS top_tier_pe_cohort_avg_los_days,
  ROUND(
    (
      tto.total_critical_labs_top_tier / tto.total_labs_measured_top_tier
    ) * 100,
    2
  ) AS critical_lab_rate_pct_top_tier_pe,
  ROUND(
    (
      gps.total_critical_labs_general_pop / gps.total_labs_measured_general_pop
    ) * 100,
    2
  ) AS critical_lab_rate_pct_general_pop
FROM
  top_tier_outcomes AS tto,
  general_population_stats AS gps;
