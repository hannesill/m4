WITH
  hhs_cohort AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON adm.subject_id = pat.subject_id
    WHERE
      pat.gender = 'F'
      AND (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year + pat.anchor_age) BETWEEN 50 AND 60
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE
          dx.hadm_id = adm.hadm_id
          AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '2502%')
            OR (dx.icd_version = 10 AND dx.icd_code LIKE 'E1_0%')
          )
      )
  ),
  critical_labs_definition AS (
    SELECT 50983 AS itemid, 'Sodium' AS lab_name, 120 AS critical_low, 160 AS critical_high UNION ALL
    SELECT 50971, 'Potassium', 2.5, 6.5 UNION ALL
    SELECT 50931, 'Glucose', 40, 600 UNION ALL
    SELECT 50912, 'Creatinine', NULL, 4.0 UNION ALL
    SELECT 51301, 'WBC', 2.0, 30.0 UNION ALL
    SELECT 50882, 'Bicarbonate', 10, 40
  ),
  all_labs_first_48h AS (
    SELECT
      le.hadm_id,
      le.itemid,
      le.valuenum
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON le.hadm_id = adm.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND DATETIME_DIFF(le.charttime, adm.admittime, HOUR) BETWEEN 0 AND 48
      AND le.itemid IN (
        SELECT itemid FROM critical_labs_definition
      )
  ),
  instability_score_calculation AS (
    SELECT
      labs.hadm_id,
      COUNT(
        DISTINCT IF(
          (
            labs.valuenum < def.critical_low
            OR labs.valuenum > def.critical_high
          ),
          labs.itemid,
          NULL
        )
      ) AS instability_score
    FROM
      all_labs_first_48h AS labs
    LEFT JOIN
      critical_labs_definition AS def
      ON labs.itemid = def.itemid
    GROUP BY
      labs.hadm_id
  ),
  hhs_cohort_scores AS (
    SELECT
      hhs.hadm_id,
      hhs.admittime,
      hhs.dischtime,
      hhs.hospital_expire_flag,
      COALESCE(scores.instability_score, 0) AS instability_score
    FROM
      hhs_cohort AS hhs
    LEFT JOIN
      instability_score_calculation AS scores
      ON hhs.hadm_id = scores.hadm_id
  ),
  hhs_percentiles AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(75)] AS p75_instability_score
    FROM
      hhs_cohort_scores
  ),
  hhs_top_tier_admissions AS (
    SELECT
      hcs.hadm_id,
      hcs.admittime,
      hcs.dischtime,
      hcs.hospital_expire_flag
    FROM
      hhs_cohort_scores AS hcs,
      hhs_percentiles AS p
    WHERE
      hcs.instability_score >= p.p75_instability_score
  ),
  top_tier_outcomes AS (
    SELECT
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS top_tier_mortality_rate,
      AVG(
        DATETIME_DIFF(dischtime, admittime, HOUR) / 24.0
      ) AS top_tier_avg_los_days
    FROM
      hhs_top_tier_admissions
  ),
  critical_lab_rates_comparison AS (
    SELECT
      t1.lab_name,
      SAFE_DIVIDE(
        COUNTIF(t1.is_top_tier_hhs = 1 AND t1.is_critical = 1),
        COUNTIF(t1.is_top_tier_hhs = 1)
      ) AS top_tier_hhs_critical_rate,
      SAFE_DIVIDE(
        COUNTIF(t1.is_top_tier_hhs = 0 AND t1.is_critical = 1),
        COUNTIF(t1.is_top_tier_hhs = 0)
      ) AS general_inpatients_critical_rate
    FROM
      (
        SELECT
          labs.hadm_id,
          def.lab_name,
          IF(
            labs.hadm_id IN (
              SELECT hadm_id FROM hhs_top_tier_admissions
            ),
            1,
            0
          ) AS is_top_tier_hhs,
          IF(
            labs.valuenum < def.critical_low
            OR labs.valuenum > def.critical_high,
            1,
            0
          ) AS is_critical
        FROM
          all_labs_first_48h AS labs
        JOIN
          critical_labs_definition AS def
          ON labs.itemid = def.itemid
      ) AS t1
    GROUP BY
      t1.lab_name
  )
SELECT
  p.p75_instability_score,
  o.top_tier_mortality_rate,
  o.top_tier_avg_los_days,
  (
    SELECT
      ARRAY_AGG(
        STRUCT(
          comp.lab_name,
          comp.top_tier_hhs_critical_rate,
          comp.general_inpatients_critical_rate
        )
      )
    FROM
      critical_lab_rates_comparison AS comp
  ) AS critical_lab_rate_comparison
FROM
  hhs_percentiles AS p,
  top_tier_outcomes AS o;
