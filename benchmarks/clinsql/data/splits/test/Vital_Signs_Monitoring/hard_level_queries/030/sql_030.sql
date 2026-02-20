WITH
  base_icustays AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      pat.gender,
      pat.anchor_age + EXTRACT(YEAR FROM icu.intime) - pat.anchor_year AS age_at_icu_intime,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
  ),
  arf_cohort_stays AS (
    SELECT DISTINCT
      base.stay_id
    FROM
      base_icustays AS base
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON base.hadm_id = dx.hadm_id
    WHERE
      base.gender = 'F'
      AND base.age_at_icu_intime BETWEEN 43 AND 53
      AND (
        (dx.icd_version = 9 AND dx.icd_code IN ('51881', '51882', '51884'))
        OR (dx.icd_version = 10 AND STARTS_WITH(dx.icd_code, 'J960'))
      )
  ),
  vitals_first_48h AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON ce.stay_id = icu.stay_id
    WHERE
      ce.itemid IN (
        220045,
        220277,
        220210,
        220052,
        220181
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
      AND ce.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 48 HOUR)
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(
        CASE
          WHEN itemid = 220045 AND valuenum > 100 THEN 1
          WHEN itemid = 220277 AND valuenum < 90 THEN 1
          WHEN itemid = 220210 AND valuenum > 22 THEN 1
          WHEN itemid IN (220052, 220181) AND valuenum < 65 THEN 1
          ELSE 0
        END
      ) AS instability_index,
      COUNTIF(itemid IN (220052, 220181) AND valuenum < 65) AS hypotension_episodes,
      COUNTIF(itemid = 220045 AND valuenum > 100) AS tachycardia_episodes
    FROM
      vitals_first_48h
    GROUP BY
      stay_id
  ),
  combined_data AS (
    SELECT
      b.stay_id,
      b.icu_los_days,
      b.hospital_expire_flag,
      COALESCE(i.instability_index, 0) AS instability_index,
      COALESCE(i.hypotension_episodes, 0) AS hypotension_episodes,
      COALESCE(i.tachycardia_episodes, 0) AS tachycardia_episodes,
      CASE
        WHEN a.stay_id IS NOT NULL THEN 1
        ELSE 0
      END AS is_target_cohort
    FROM
      base_icustays AS b
    LEFT JOIN
      instability_scores AS i
      ON b.stay_id = i.stay_id
    LEFT JOIN
      arf_cohort_stays AS a
      ON b.stay_id = a.stay_id
  ),
  target_cohort_percentiles AS (
    SELECT
      APPROX_QUANTILES(instability_index, 100)[OFFSET(95)] AS p95_instability_index,
      APPROX_QUANTILES(instability_index, 4)[OFFSET(3)] AS q3_instability_threshold
    FROM
      combined_data
    WHERE
      is_target_cohort = 1
  ),
  comparison_groups AS (
    SELECT
      'Top Quartile Target Cohort' AS group_name,
      COUNT(stay_id) AS num_patients,
      AVG(hypotension_episodes) AS avg_hypotension_episodes,
      AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(icu_los_days) AS avg_icu_los_days,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
    FROM
      combined_data
    WHERE
      is_target_cohort = 1
      AND instability_index >= (SELECT q3_instability_threshold FROM target_cohort_percentiles)
    UNION ALL
    SELECT
      'General ICU Population' AS group_name,
      COUNT(stay_id) AS num_patients,
      AVG(hypotension_episodes) AS avg_hypotension_episodes,
      AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(icu_los_days) AS avg_icu_los_days,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
    FROM
      combined_data
  )
SELECT
  p.p95_instability_index AS target_cohort_p95_instability_index,
  c.group_name,
  c.num_patients,
  c.avg_hypotension_episodes,
  c.avg_tachycardia_episodes,
  c.avg_icu_los_days,
  c.mortality_rate
FROM
  comparison_groups AS c
CROSS JOIN
  target_cohort_percentiles AS p;
