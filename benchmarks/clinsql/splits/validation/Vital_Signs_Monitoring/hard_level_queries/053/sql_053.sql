WITH
  icd_shock AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 10 AND (
        icd_code LIKE 'R57%'
        OR icd_code LIKE 'A41%'
        OR icd_code = 'T81.12'
      ))
      OR
      (icd_version = 9 AND (
        icd_code = '785.50'
        OR icd_code = '785.51'
        OR icd_code = '785.52'
        OR icd_code = '785.59'
        OR icd_code = '998.0'
      ))
  ),
  base_cohort AS (
    SELECT
      p.subject_id,
      p.gender,
      p.anchor_age,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON icu.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 59 AND 69
  ),
  cohorts AS (
    SELECT
      bc.subject_id,
      bc.hadm_id,
      bc.stay_id,
      bc.intime,
      bc.icu_los_hours,
      adm.hospital_expire_flag,
      CASE
        WHEN shock.hadm_id IS NOT NULL THEN 'Target_Female_59_69_Shock'
        ELSE 'Control_Female_59_69_NoShock'
      END AS cohort_group
    FROM
      base_cohort AS bc
    LEFT JOIN
      icd_shock AS shock
      ON bc.hadm_id = shock.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON bc.hadm_id = adm.hadm_id
  ),
  vitals_first_24h AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      cohorts AS co
      ON ce.stay_id = co.stay_id
    WHERE
      ce.charttime BETWEEN co.intime AND DATETIME_ADD(co.intime, INTERVAL 24 HOUR)
      AND ce.itemid IN (
        220052,
        225312,
        220045
      )
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
  ),
  abnormal_flags AS (
    SELECT
      stay_id,
      CASE
        WHEN itemid IN (220052, 225312) AND valuenum < 65 THEN 1
        ELSE 0
      END AS is_hypotensive,
      CASE
        WHEN itemid = 220045 AND valuenum > 100 THEN 1
        ELSE 0
      END AS is_tachycardic
    FROM
      vitals_first_24h
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(is_hypotensive) AS hypotensive_episodes,
      SUM(is_tachycardic) AS tachycardic_episodes,
      (SUM(is_hypotensive) + SUM(is_tachycardic)) AS composite_instability_score
    FROM
      abnormal_flags
    GROUP BY
      stay_id
  ),
  final_data AS (
    SELECT
      co.cohort_group,
      co.stay_id,
      co.icu_los_hours,
      co.hospital_expire_flag,
      COALESCE(iss.composite_instability_score, 0) AS composite_instability_score,
      COALESCE(iss.hypotensive_episodes, 0) AS hypotensive_episodes,
      COALESCE(iss.tachycardic_episodes, 0) AS tachycardic_episodes
    FROM
      cohorts AS co
    LEFT JOIN
      instability_scores AS iss
      ON co.stay_id = iss.stay_id
  )
SELECT
  cohort_group,
  COUNT(DISTINCT stay_id) AS patient_count,
  AVG(composite_instability_score) AS avg_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(25)] AS p25_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(50)] AS p50_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(75)] AS p75_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(95)] AS p95_instability_score,
  AVG(hypotensive_episodes) AS avg_hypotensive_episodes_burden,
  AVG(tachycardic_episodes) AS avg_tachycardic_episodes_burden,
  AVG(icu_los_hours) AS avg_icu_los_hours,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
FROM
  final_data
GROUP BY
  cohort_group
ORDER BY
  cohort_group DESC;
