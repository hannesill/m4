WITH
  target_cohort_stays AS (
    SELECT DISTINCT
      icu.stay_id
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON icu.hadm_id = dx.hadm_id
    WHERE
      pat.gender = 'M'
      AND (EXTRACT(YEAR FROM icu.intime) - pat.anchor_year + pat.anchor_age BETWEEN 82 AND 92)
      AND (
        STARTS_WITH(dx.icd_code, '51881')
        OR STARTS_WITH(dx.icd_code, '51882')
        OR STARTS_WITH(dx.icd_code, '51884')
        OR STARTS_WITH(dx.icd_code, 'J960')
      )
  ),
  vitals_raw AS (
    SELECT
      stay_id,
      charttime,
      itemid,
      valuenum
    FROM `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
      itemid IN (
        220045,
        220052,
        220181,
        225312
      )
      AND valuenum IS NOT NULL
      AND valuenum > 0
  ),
  vitals_first_72h AS (
    SELECT
      v.stay_id,
      CASE
        WHEN v.itemid IN (220052, 220181, 225312) AND v.valuenum < 65
        THEN 1
        ELSE 0
      END AS is_hypotensive,
      CASE
        WHEN v.itemid = 220045 AND v.valuenum > 100
        THEN 1
        ELSE 0
      END AS is_tachycardic,
      CASE WHEN v.itemid = 220045 THEN 1 ELSE 0 END AS is_hr_measurement,
      CASE WHEN v.itemid IN (220052, 220181, 225312) THEN 1 ELSE 0 END AS is_map_measurement
    FROM vitals_raw AS v
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON v.stay_id = icu.stay_id
    WHERE
      v.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SAFE_DIVIDE(SUM(is_hypotensive), SUM(is_map_measurement)) AS hypotension_burden,
      SAFE_DIVIDE(SUM(is_tachycardic), SUM(is_hr_measurement)) AS tachycardia_burden
    FROM vitals_first_72h
    GROUP BY
      stay_id
  ),
  combined_data AS (
    SELECT
      icu.stay_id,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days,
      COALESCE(sc.hypotension_burden, 0) + COALESCE(sc.tachycardia_burden, 0) AS instability_score,
      COALESCE(sc.hypotension_burden, 0) AS hypotension_burden,
      COALESCE(sc.tachycardia_burden, 0) AS tachycardia_burden,
      CASE WHEN tgt.stay_id IS NOT NULL THEN 1 ELSE 0 END AS is_target_cohort
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    LEFT JOIN instability_scores AS sc
      ON icu.stay_id = sc.stay_id
    LEFT JOIN target_cohort_stays AS tgt
      ON icu.stay_id = tgt.stay_id
  )
SELECT
  CASE
    WHEN is_target_cohort = 1 THEN 'Target Cohort (Male, 82-92, ARF)'
    ELSE 'General ICU Population (Control)'
  END AS cohort_group,
  COUNT(stay_id) AS total_stays,
  AVG(instability_score) AS avg_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(25)] AS p25_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(50)] AS median_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(75)] AS p75_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(75)] - APPROX_QUANTILES(instability_score, 100)[OFFSET(25)] AS iqr_instability_score,
  AVG(hypotension_burden) AS avg_hypotension_burden,
  AVG(tachycardia_burden) AS avg_tachycardia_burden,
  AVG(icu_los_days) AS avg_icu_los_days,
  AVG(hospital_expire_flag) AS mortality_rate
FROM combined_data
GROUP BY
  cohort_group
ORDER BY
  cohort_group DESC
