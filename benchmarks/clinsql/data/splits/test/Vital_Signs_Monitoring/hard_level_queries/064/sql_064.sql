WITH
target_cohort_stays AS (
  SELECT
    icu.stay_id
  FROM
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON icu.subject_id = pat.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON icu.hadm_id = dx.hadm_id
  WHERE
    pat.gender = 'M'
    AND pat.anchor_age BETWEEN 45 AND 55
    AND (
      dx.icd_code LIKE 'J960%'
      OR dx.icd_code = '51881'
    )
  GROUP BY
    icu.stay_id
),
control_cohort_stays AS (
  SELECT
    icu.stay_id
  FROM
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON icu.subject_id = pat.subject_id
  WHERE
    pat.anchor_age BETWEEN 45 AND 55
  GROUP BY
    icu.stay_id
),
all_cohort_stays AS (
  SELECT stay_id FROM target_cohort_stays
  UNION DISTINCT
  SELECT stay_id FROM control_cohort_stays
),
vitals_first_48h AS (
  SELECT
    ce.stay_id,
    ce.charttime,
    MAX(CASE WHEN ce.itemid = 220045 THEN ce.valuenum END) AS hr,
    MAX(CASE WHEN ce.itemid IN (220052, 220181, 225312) THEN ce.valuenum END) AS map
  FROM
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON ce.stay_id = icu.stay_id
  WHERE
    ce.stay_id IN (SELECT stay_id FROM all_cohort_stays)
    AND ce.itemid IN (
      220045,
      220052,
      220181,
      225312
    )
    AND DATETIME_DIFF(ce.charttime, icu.intime, HOUR) BETWEEN 0 AND 48
    AND ce.valuenum > 0 AND ce.valuenum < 350
  GROUP BY
    ce.stay_id,
    ce.charttime
),
instability_scores AS (
  SELECT
    stay_id,
    COALESCE(STDDEV_SAMP(hr), 0) + COALESCE(STDDEV_SAMP(map), 0) AS instability_score,
    COUNTIF(map < 65) AS hypotension_episodes,
    COUNTIF(hr > 100) AS tachycardia_episodes
  FROM
    vitals_first_48h
  WHERE hr IS NOT NULL AND map IS NOT NULL
  GROUP BY
    stay_id
  HAVING COUNT(stay_id) > 1
),
enriched_data AS (
  SELECT
    sc.stay_id,
    sc.instability_score,
    sc.hypotension_episodes,
    sc.tachycardia_episodes,
    DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days,
    adm.hospital_expire_flag,
    CASE
      WHEN ts.stay_id IS NOT NULL THEN 'Target (Male, 45-55, ARF)'
      ELSE 'Control (All, 45-55)'
    END AS cohort_group,
    CASE
      WHEN ts.stay_id IS NOT NULL THEN NTILE(4) OVER (PARTITION BY (CASE WHEN ts.stay_id IS NOT NULL THEN 1 ELSE 0 END) ORDER BY sc.instability_score DESC)
      ELSE NULL
    END AS instability_quartile,
    CASE
      WHEN ts.stay_id IS NOT NULL THEN PERCENTILE_CONT(sc.instability_score, 0.95) OVER (PARTITION BY (CASE WHEN ts.stay_id IS NOT NULL THEN 1 ELSE 0 END))
      ELSE NULL
    END AS p95_instability_score_target
  FROM
    instability_scores AS sc
  LEFT JOIN
    target_cohort_stays AS ts ON sc.stay_id = ts.stay_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON sc.stay_id = icu.stay_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
  WHERE
    sc.stay_id IN (SELECT stay_id FROM all_cohort_stays)
),
target_top_quartile_agg AS (
  SELECT
    'Target Top Quartile (Male, 45-55, ARF, Top 25% Instability)' AS cohort_name,
    COUNT(DISTINCT stay_id) AS num_patients,
    AVG(instability_score) AS avg_instability_score,
    ANY_VALUE(p95_instability_score_target) AS p95_instability_score_for_target_group,
    AVG(hypotension_episodes) AS avg_hypotension_episodes,
    AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
  FROM
    enriched_data
  WHERE
    cohort_group = 'Target (Male, 45-55, ARF)'
    AND instability_quartile = 1
),
control_cohort_agg AS (
  SELECT
    'Control (All, 45-55)' AS cohort_name,
    COUNT(DISTINCT stay_id) AS num_patients,
    AVG(instability_score) AS avg_instability_score,
    NULL AS p95_instability_score_for_target_group,
    AVG(hypotension_episodes) AS avg_hypotension_episodes,
    AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
  FROM
    enriched_data
  WHERE
    cohort_group = 'Control (All, 45-55)'
)
SELECT * FROM target_top_quartile_agg
UNION ALL
SELECT * FROM control_cohort_agg;
