WITH
  icu_cohort AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      icu.stay_id,
      icu.intime,
      DATETIME_DIFF(icu.outtime, icu.intime, DAY) AS icu_los_days,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
        ON icu.hadm_id = adm.hadm_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
        ON icu.subject_id = pat.subject_id
    WHERE
      pat.gender = 'M'
      AND (
        EXTRACT(YEAR FROM icu.intime) - pat.anchor_year + pat.anchor_age
      ) BETWEEN 60 AND 70
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY adm.hadm_id
        ORDER BY
          icu.intime
      ) = 1
  ),
  ugib_stays AS (
    SELECT DISTINCT
      co.stay_id
    FROM
      icu_cohort AS co
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        ON co.hadm_id = dx.hadm_id
    WHERE
      (
        dx.icd_version = 9
        AND (
          dx.icd_code LIKE '578%'
          OR dx.icd_code LIKE '531.0%'
          OR dx.icd_code LIKE '531.2%'
          OR dx.icd_code LIKE '531.4%'
          OR dx.icd_code LIKE '531.6%'
          OR dx.icd_code LIKE '532.0%'
          OR dx.icd_code LIKE '532.4%'
        )
      )
      OR (
        dx.icd_version = 10
        AND (
          dx.icd_code LIKE 'K92.0%'
          OR dx.icd_code LIKE 'K92.1%'
          OR dx.icd_code LIKE 'K92.2%'
          OR dx.icd_code LIKE 'K25.0%'
          OR dx.icd_code LIKE 'K25.4%'
          OR dx.icd_code LIKE 'K26.0%'
          OR dx.icd_code LIKE 'K26.4%'
        )
      )
  ),
  vitals_filtered AS (
    SELECT
      ch.stay_id,
      ch.itemid,
      ch.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ch
      INNER JOIN icu_cohort AS co
        ON ch.stay_id = co.stay_id
    WHERE
      ch.itemid IN (
        220045,
        220181,
        225312,
        220210
      )
      AND ch.charttime BETWEEN co.intime AND DATETIME_ADD(co.intime, INTERVAL 48 HOUR)
      AND ch.valuenum IS NOT NULL
      AND ch.valuenum > 0
  ),
  abnormal_episodes AS (
    SELECT
      stay_id,
      SUM(
        CASE
          WHEN itemid = 220045 AND valuenum > 100
          THEN 1
          ELSE 0
        END
      ) AS tachycardia_episodes,
      SUM(
        CASE
          WHEN itemid IN (220181, 225312) AND valuenum < 65
          THEN 1
          ELSE 0
        END
      ) AS hypotension_episodes,
      SUM(
        CASE
          WHEN itemid = 220210 AND valuenum > 20
          THEN 1
          ELSE 0
        END
      ) AS tachypnea_episodes
    FROM
      vitals_filtered
    GROUP BY
      stay_id
  ),
  cohort_scores AS (
    SELECT
      co.stay_id,
      co.icu_los_days,
      co.hospital_expire_flag,
      CASE
        WHEN ug.stay_id IS NOT NULL
        THEN 'UGIB_60_70_Male'
        ELSE 'Control_60_70_Male'
      END AS cohort_group,
      COALESCE(ep.tachycardia_episodes, 0) AS tachycardia_episodes,
      COALESCE(ep.hypotension_episodes, 0) AS hypotension_episodes,
      COALESCE(ep.tachypnea_episodes, 0) AS tachypnea_episodes,
      (
        COALESCE(ep.tachycardia_episodes, 0) + COALESCE(ep.hypotension_episodes, 0) + COALESCE(ep.tachypnea_episodes, 0)
      ) AS vital_instability_index
    FROM
      icu_cohort AS co
      LEFT JOIN abnormal_episodes AS ep
        ON co.stay_id = ep.stay_id
      LEFT JOIN ugib_stays AS ug
        ON co.stay_id = ug.stay_id
  ),
  ranked_cohorts AS (
    SELECT
      *,
      NTILE(10) OVER (
        PARTITION BY
          cohort_group
        ORDER BY
          vital_instability_index DESC
      ) AS instability_decile,
      PERCENTILE_CONT(vital_instability_index, 0.95) OVER (
        PARTITION BY
          cohort_group
      ) AS p95_instability_index
    FROM
      cohort_scores
  ),
  ugib_percentile_value AS (
    SELECT DISTINCT
      p95_instability_index
    FROM
      ranked_cohorts
    WHERE
      cohort_group = 'UGIB_60_70_Male'
  ),
  final_comparison AS (
    SELECT
      'UGIB_Top_Decile' AS comparison_group,
      COUNT(stay_id) AS num_patients,
      AVG(vital_instability_index) AS avg_instability_index,
      AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(hypotension_episodes) AS avg_hypotension_episodes,
      AVG(tachypnea_episodes) AS avg_tachypnea_episodes,
      AVG(icu_los_days) AS avg_icu_los_days,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
    FROM
      ranked_cohorts
    WHERE
      cohort_group = 'UGIB_60_70_Male' AND instability_decile = 1
    UNION ALL
    SELECT
      'Control_Age_Matched' AS comparison_group,
      COUNT(stay_id) AS num_patients,
      AVG(vital_instability_index) AS avg_instability_index,
      AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(hypotension_episodes) AS avg_hypotension_episodes,
      AVG(tachypnea_episodes) AS avg_tachypnea_episodes,
      AVG(icu_los_days) AS avg_icu_los_days,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
    FROM
      ranked_cohorts
    WHERE
      cohort_group = 'Control_60_70_Male'
  )
SELECT
  p.p95_instability_index AS ugib_cohort_95th_percentile_instability_index,
  c.comparison_group,
  c.num_patients,
  ROUND(c.avg_instability_index, 2) AS avg_instability_index,
  ROUND(c.avg_tachycardia_episodes, 2) AS avg_tachycardia_episodes,
  ROUND(c.avg_hypotension_episodes, 2) AS avg_hypotension_episodes,
  ROUND(c.avg_tachypnea_episodes, 2) AS avg_tachypnea_episodes,
  ROUND(c.avg_icu_los_days, 2) AS avg_icu_los_days,
  ROUND(c.mortality_rate, 4) AS mortality_rate
FROM
  final_comparison AS c
  CROSS JOIN ugib_percentile_value AS p
ORDER BY
  c.comparison_group DESC;
