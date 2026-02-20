WITH
  icd_hf AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '428')
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I50')
  ),
  icustays_base AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      pat.gender,
      (EXTRACT(YEAR FROM icu.intime) - pat.anchor_year) + pat.anchor_age AS age_at_icu_admission,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours,
      adm.hospital_expire_flag
    FROM
      (
        SELECT
          *,
          ROW_NUMBER() OVER(PARTITION BY hadm_id ORDER BY intime) AS stay_rank
        FROM
          `physionet-data.mimiciv_3_1_icu.icustays`
      ) AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON icu.subject_id = pat.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
    WHERE
      icu.stay_rank = 1
  ),
  cohort_hf_target AS (
    SELECT
      b.stay_id,
      b.intime
    FROM
      icustays_base AS b
    INNER JOIN
      icd_hf ON b.hadm_id = icd_hf.hadm_id
    WHERE
      b.gender = 'M'
      AND b.age_at_icu_admission BETWEEN 45 AND 55
  ),
  vitals_first_72h AS (
    SELECT
      ce.stay_id,
      CASE
        WHEN ce.itemid = 220045 AND ce.valuenum > 100 THEN 1
        ELSE 0
      END AS is_tachycardic,
      CASE
        WHEN ce.itemid IN (220052, 220181, 225312) AND ce.valuenum < 65 THEN 1
        ELSE 0
      END AS is_hypotensive,
      CASE
        WHEN ce.itemid IN (220210, 224690) AND ce.valuenum > 20 THEN 1
        ELSE 0
      END AS is_tachypneic
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      icustays_base AS icu ON ce.stay_id = icu.stay_id
    WHERE
      ce.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
      AND ce.itemid IN (220045, 220052, 220181, 225312, 220210, 224690)
      AND ce.valuenum IS NOT NULL AND ce.valuenum > 0
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(is_tachycardic) AS tachycardia_episodes,
      SUM(is_hypotensive) AS hypotension_episodes,
      SUM(is_tachypneic) AS tachypnea_episodes,
      (SUM(is_tachycardic) + SUM(is_hypotensive) + SUM(is_tachypneic)) AS composite_instability_score
    FROM
      vitals_first_72h
    GROUP BY
      stay_id
  ),
  ranked_hf_cohort AS (
    SELECT
      sc.stay_id,
      sc.composite_instability_score,
      sc.tachycardia_episodes,
      sc.hypotension_episodes,
      sc.tachypnea_episodes,
      PERCENTILE_CONT(sc.composite_instability_score, 0.99) OVER() AS p99_instability_score_cohort,
      NTILE(4) OVER(ORDER BY sc.composite_instability_score DESC) AS instability_quartile
    FROM
      instability_scores AS sc
    INNER JOIN
      cohort_hf_target AS hf ON sc.stay_id = hf.stay_id
  ),
  cohort_unstable_quartile_stats AS (
    SELECT
      'Unstable HF Cohort (Top Quartile)' AS comparison_group,
      MAX(r.p99_instability_score_cohort) AS p99_instability_score_for_hf_cohort,
      AVG(r.tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(r.hypotension_episodes) AS avg_hypotension_episodes,
      AVG(r.tachypnea_episodes) AS avg_tachypnea_episodes,
      AVG(icu.icu_los_hours) AS avg_icu_los_hours,
      AVG(CAST(icu.hospital_expire_flag AS FLOAT64)) AS mortality_rate
    FROM
      ranked_hf_cohort AS r
    INNER JOIN
      icustays_base AS icu ON r.stay_id = icu.stay_id
    WHERE
      r.instability_quartile = 1
    GROUP BY
      comparison_group
  ),
  general_icu_stats AS (
    SELECT
      'General ICU Population' AS comparison_group,
      NULL AS p99_instability_score_for_hf_cohort,
      AVG(sc.tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(sc.hypotension_episodes) AS avg_hypotension_episodes,
      AVG(sc.tachypnea_episodes) AS avg_tachypnea_episodes,
      AVG(icu.icu_los_hours) AS avg_icu_los_hours,
      AVG(CAST(icu.hospital_expire_flag AS FLOAT64)) AS mortality_rate
    FROM
      instability_scores AS sc
    INNER JOIN
      icustays_base AS icu ON sc.stay_id = icu.stay_id
    GROUP BY
      comparison_group
  )
SELECT
  *
FROM
  cohort_unstable_quartile_stats
UNION ALL
SELECT
  *
FROM
  general_icu_stats;
