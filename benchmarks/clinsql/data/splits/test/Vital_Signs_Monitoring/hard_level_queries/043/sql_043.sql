WITH
  icustay_details AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours,
      pat.gender,
      DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age AS age_at_icu_intime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON icu.subject_id = pat.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
  ),
  respiratory_failure_stays AS (
    SELECT DISTINCT
      id.stay_id
    FROM
      icustay_details AS id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON id.hadm_id = dx.hadm_id
    WHERE
      (
        dx.icd_version = 9
        AND STARTS_WITH(dx.icd_code, '5188')
      )
      OR (
        dx.icd_version = 10
        AND STARTS_WITH(dx.icd_code, 'J96')
      )
  ),
  cohorts AS (
    SELECT
      id.stay_id,
      id.intime,
      id.icu_los_hours,
      id.hospital_expire_flag,
      CASE
        WHEN id.gender = 'M' AND id.age_at_icu_intime BETWEEN 40 AND 50 THEN 'Target (Male, 40-50, Resp Failure)'
        ELSE 'Comparison (Other Resp Failure)'
      END AS cohort_group
    FROM
      icustay_details AS id
    WHERE
      id.stay_id IN (
        SELECT
          stay_id
        FROM
          respiratory_failure_stays
      )
  ),
  filtered_vitals AS (
    SELECT
      c.stay_id,
      c.cohort_group,
      ce.itemid,
      ce.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      INNER JOIN cohorts AS c ON ce.stay_id = c.stay_id
    WHERE
      ce.itemid IN (
        220045,
        220052,
        225312,
        224690
      )
      AND DATETIME_DIFF(ce.charttime, c.intime, HOUR) BETWEEN 0 AND 48
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
  ),
  abnormal_events AS (
    SELECT
      stay_id,
      cohort_group,
      CASE
        WHEN itemid IN (
          220052, 225312, 224690
        )
        AND valuenum < 65 THEN 1
        ELSE 0
      END AS is_hypotensive,
      CASE
        WHEN itemid = 220045 AND valuenum > 100 THEN 1
        ELSE 0
      END AS is_tachycardic
    FROM
      filtered_vitals
  ),
  patient_level_instability AS (
    SELECT
      ae.stay_id,
      c.cohort_group,
      c.icu_los_hours,
      c.hospital_expire_flag,
      SUM(ae.is_hypotensive) AS hypotensive_episodes,
      SUM(ae.is_tachycardic) AS tachycardic_episodes,
      SUM(ae.is_hypotensive) + SUM(ae.is_tachycardic) AS vital_instability_index
    FROM
      abnormal_events AS ae
      INNER JOIN cohorts AS c ON ae.stay_id = c.stay_id
    GROUP BY
      ae.stay_id,
      c.cohort_group,
      c.icu_los_hours,
      c.hospital_expire_flag
  )
SELECT
  cohort_group,
  COUNT(DISTINCT stay_id) AS num_patients,
  ROUND(AVG(vital_instability_index), 2) AS avg_instability_index,
  ROUND(STDDEV(vital_instability_index), 2) AS stddev_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(25)] AS p25_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(50)] AS p50_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(75)] AS p75_instability_index,
  APPROX_QUANTILES(vital_instability_index, 100)[OFFSET(95)] AS p95_instability_index,
  ROUND(AVG(hypotensive_episodes), 2) AS avg_hypotensive_episodes,
  ROUND(AVG(tachycardic_episodes), 2) AS avg_tachycardic_episodes,
  ROUND(AVG(icu_los_hours), 2) AS avg_icu_los_hours,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent
FROM
  patient_level_instability
GROUP BY
  cohort_group
ORDER BY
  cohort_group DESC;
