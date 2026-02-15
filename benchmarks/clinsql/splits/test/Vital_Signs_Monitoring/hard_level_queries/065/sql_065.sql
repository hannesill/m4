WITH
item_ids AS (
  SELECT
    [220052, 220181] AS map_ids,
    [220045] AS hr_ids,
    [
      225802,
      225803,
      225805,
      224149,
      224150,
      224151,
      224152,
      225977,
      224144,
      224145
    ] AS rrt_ids
),
base_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    icu.stay_id,
    icu.intime,
    icu.outtime,
    DATETIME_DIFF(icu.outtime, icu.intime, DAY) AS icu_los_days,
    a.hospital_expire_flag
  FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON icu.hadm_id = a.hadm_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON icu.subject_id = p.subject_id
  WHERE
    p.gender = 'M'
    AND (DATETIME_DIFF(icu.intime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) BETWEEN 70 AND 80
),
rrt_stays AS (
  SELECT DISTINCT stay_id
  FROM `physionet-data.mimiciv_3_1_icu.chartevents`
  CROSS JOIN item_ids
  WHERE
    itemid IN UNNEST(item_ids.rrt_ids)
    AND stay_id IN (SELECT stay_id FROM base_cohort)
),
cohort_with_rrt_flag AS (
  SELECT
    bc.*,
    CASE WHEN rs.stay_id IS NOT NULL THEN 1 ELSE 0 END AS has_rrt
  FROM base_cohort AS bc
  LEFT JOIN rrt_stays AS rs
    ON bc.stay_id = rs.stay_id
),
vitals_first_48h AS (
  SELECT
    c.stay_id,
    CASE
      WHEN ce.itemid IN UNNEST(i.map_ids) AND ce.valuenum < 65 THEN 1
      ELSE 0
    END AS is_hypotensive,
    CASE
      WHEN ce.itemid IN UNNEST(i.hr_ids) AND ce.valuenum > 100 THEN 1
      ELSE 0
    END AS is_tachycardic,
    CASE
      WHEN ce.itemid IN UNNEST(i.map_ids) OR ce.itemid IN UNNEST(i.hr_ids) THEN 1
      ELSE 0
    END AS is_vital_measurement
  FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
  INNER JOIN cohort_with_rrt_flag AS c
    ON ce.stay_id = c.stay_id
  CROSS JOIN item_ids AS i
  WHERE
    ce.charttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 48 HOUR)
    AND ce.itemid IN UNNEST(ARRAY_CONCAT(i.map_ids, i.hr_ids))
    AND ce.valuenum IS NOT NULL
),
instability_scores AS (
  SELECT
    stay_id,
    SUM(is_hypotensive) AS hypotensive_episodes,
    SUM(is_tachycardic) AS tachycardic_episodes,
    SAFE_DIVIDE(
      SUM(is_hypotensive) + SUM(is_tachycardic),
      SUM(is_vital_measurement)
    ) AS instability_score
  FROM vitals_first_48h
  GROUP BY stay_id
),
full_cohort_data AS (
  SELECT
    c.stay_id,
    c.has_rrt,
    c.icu_los_days,
    c.hospital_expire_flag,
    COALESCE(i.instability_score, 0) AS instability_score,
    COALESCE(i.hypotensive_episodes, 0) AS hypotensive_episodes,
    COALESCE(i.tachycardic_episodes, 0) AS tachycardic_episodes
  FROM cohort_with_rrt_flag AS c
  LEFT JOIN instability_scores AS i
    ON c.stay_id = i.stay_id
),
p90_score_rrt_cohort AS (
  SELECT
    APPROX_QUANTILES(instability_score, 100)[OFFSET(90)] AS p90_instability_score
  FROM full_cohort_data
  WHERE has_rrt = 1
),
rrt_cohort_ranked AS (
  SELECT
    *,
    NTILE(10) OVER (ORDER BY instability_score DESC) AS score_decile
  FROM full_cohort_data
  WHERE has_rrt = 1
),
top_decile_rrt_stats AS (
  SELECT
    'Top 10% Instability (RRT Cohort)' AS cohort_group,
    COUNT(stay_id) AS patient_count,
    AVG(hypotensive_episodes) AS avg_hypotension_episodes,
    AVG(tachycardic_episodes) AS avg_tachycardia_episodes,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
  FROM rrt_cohort_ranked
  WHERE score_decile = 1
),
comparison_cohort_stats AS (
  SELECT
    'Comparison Cohort (No RRT)' AS cohort_group,
    COUNT(stay_id) AS patient_count,
    AVG(hypotensive_episodes) AS avg_hypotension_episodes,
    AVG(tachycardic_episodes) AS avg_tachycardia_episodes,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
  FROM full_cohort_data
  WHERE has_rrt = 0
)
SELECT
  p90.p90_instability_score,
  s.cohort_group,
  s.patient_count,
  s.avg_hypotension_episodes,
  s.avg_tachycardia_episodes,
  s.avg_icu_los_days,
  s.mortality_rate
FROM (
  SELECT * FROM top_decile_rrt_stats
  UNION ALL
  SELECT * FROM comparison_cohort_stats
) AS s
CROSS JOIN p90_score_rrt_cohort AS p90
ORDER BY s.cohort_group DESC
