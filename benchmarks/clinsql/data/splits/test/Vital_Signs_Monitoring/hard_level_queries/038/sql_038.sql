WITH
  icu_cohorts AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days,
      CASE
        WHEN
          (EXTRACT(YEAR FROM icu.intime) - pat.anchor_year) + pat.anchor_age BETWEEN 63 AND 73
          AND pat.gender = 'F'
          AND icu.hadm_id IN (
            SELECT DISTINCT hadm_id
            FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
            WHERE
              icd_code = '3453'
              OR icd_code LIKE 'G41%'
          )
          THEN 'Status_Epilepticus_63_73_F'
        ELSE 'General_ICU_Population'
      END AS cohort_group
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
  ),
  vitals_first_72h AS (
    SELECT
      coh.stay_id,
      coh.cohort_group,
      ce.itemid,
      ce.valuenum
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN icu_cohorts AS coh
      ON ce.stay_id = coh.stay_id
    WHERE
      ce.charttime >= coh.intime AND ce.charttime <= DATETIME_ADD(coh.intime, INTERVAL 72 HOUR)
      AND ce.itemid IN (
        220045,
        220052, 220181, 225312,
        220210, 224690,
        220277, 646,
        223762,
        223761
      )
      AND ce.valuenum IS NOT NULL
  ),
  abnormal_events AS (
    SELECT
      stay_id,
      cohort_group,
      CASE
        WHEN itemid = 220045 AND valuenum > 100 THEN 1
        ELSE 0
      END AS is_tachycardia,
      CASE
        WHEN itemid IN (220052, 220181, 225312) AND valuenum < 65 THEN 1
        ELSE 0
      END AS is_hypotension,
      CASE
        WHEN itemid IN (220210, 224690) AND (valuenum > 22 OR valuenum < 10) THEN 1
        WHEN itemid IN (220277, 646) AND valuenum < 92 THEN 1
        WHEN itemid = 223762 AND (valuenum > 38.3 OR valuenum < 36.0) THEN 1
        WHEN itemid = 223761 AND (((valuenum - 32) * 5.0 / 9.0) > 38.3 OR ((valuenum - 32) * 5.0 / 9.0) < 36.0) THEN 1
        ELSE 0
      END AS is_other_abnormal
    FROM vitals_first_72h
  ),
  patient_scores AS (
    SELECT
      stay_id,
      cohort_group,
      SUM(is_tachycardia) AS tachycardia_episodes,
      SUM(is_hypotension) AS hypotension_episodes,
      SUM(is_tachycardia) + SUM(is_hypotension) + SUM(is_other_abnormal) AS vital_instability_index
    FROM abnormal_events
    GROUP BY
      stay_id,
      cohort_group
  ),
  final_stats_per_patient AS (
    SELECT
      coh.cohort_group,
      coh.stay_id,
      COALESCE(ps.vital_instability_index, 0) AS vital_instability_index,
      COALESCE(ps.tachycardia_episodes, 0) AS tachycardia_episodes,
      COALESCE(ps.hypotension_episodes, 0) AS hypotension_episodes,
      coh.icu_los_days,
      coh.hospital_expire_flag
    FROM icu_cohorts AS coh
    LEFT JOIN patient_scores AS ps
      ON coh.stay_id = ps.stay_id
  )
SELECT
  cohort_group,
  COUNT(DISTINCT stay_id) AS num_patients,
  AVG(vital_instability_index) AS avg_vital_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(25)] AS p25_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(50)] AS p50_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(75)] AS p75_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(90)] AS p90_instability_index,
  AVG(tachycardia_episodes) AS avg_tachycardia_episodes_per_stay,
  AVG(hypotension_episodes) AS avg_hypotension_episodes_per_stay,
  AVG(icu_los_days) AS avg_icu_los_days,
  AVG(CAST(hospital_expire_flag AS INT64)) * 100 AS mortality_rate_percent
FROM final_stats_per_patient
GROUP BY
  cohort_group
ORDER BY
  cohort_group DESC;
