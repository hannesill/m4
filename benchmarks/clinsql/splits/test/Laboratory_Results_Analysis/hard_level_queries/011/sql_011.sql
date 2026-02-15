WITH
  aki_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code IN ('5845', '5846', '5847', '5848', '5849')
      OR icd_code LIKE 'N17%'
  ),
  base_cohorts AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      CASE
        WHEN aki.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS is_aki_patient
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
      LEFT JOIN aki_diagnoses AS aki ON adm.hadm_id = aki.hadm_id
    WHERE
      pat.gender = 'M'
      AND (
        DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age
      ) BETWEEN 47 AND 57
  ),
  relevant_labevents AS (
    SELECT
      le.hadm_id,
      le.valuenum,
      CASE
        WHEN le.itemid IN (50983, 50824) THEN 'sodium'
        WHEN le.itemid IN (50971, 50822) THEN 'potassium'
        WHEN le.itemid = 50912 THEN 'creatinine'
        WHEN le.itemid = 50813 THEN 'lactate'
        WHEN le.itemid IN (51301, 51300) THEN 'wbc'
        WHEN le.itemid IN (51222, 50811) THEN 'hemoglobin'
        WHEN le.itemid = 51265 THEN 'platelet'
        ELSE NULL
      END AS lab_name
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN base_cohorts AS bc ON le.hadm_id = bc.hadm_id
    WHERE
      le.charttime BETWEEN bc.admittime AND DATETIME_ADD(bc.admittime, INTERVAL 72 HOUR)
      AND le.itemid IN (
        50983, 50824,
        50971, 50822,
        50912,
        50813,
        51301, 51300,
        51222, 50811,
        51265
      )
      AND le.valuenum IS NOT NULL
  ),
  lab_abnormalities AS (
    SELECT
      hadm_id,
      CASE
        WHEN lab_name = 'sodium' AND (valuenum < 125 OR valuenum > 155) THEN 1
        WHEN lab_name = 'potassium' AND (valuenum < 3.0 OR valuenum > 6.0) THEN 1
        WHEN lab_name = 'creatinine' AND valuenum > 2.0 THEN 1
        WHEN lab_name = 'lactate' AND valuenum > 4.0 THEN 1
        WHEN lab_name = 'wbc' AND (valuenum < 2.0 OR valuenum > 20.0) THEN 1
        WHEN lab_name = 'hemoglobin' AND valuenum < 7.0 THEN 1
        WHEN lab_name = 'platelet' AND valuenum < 50 THEN 1
        ELSE 0
      END AS is_critical
    FROM
      relevant_labevents
    WHERE
      lab_name IS NOT NULL
  ),
  patient_level_summary AS (
    WITH
      critical_counts AS (
        SELECT
          hadm_id,
          SUM(is_critical) AS instability_score
        FROM
          lab_abnormalities
        GROUP BY
          hadm_id
      ),
      total_counts AS (
        SELECT
          hadm_id,
          COUNT(*) AS total_lab_tests
        FROM
          relevant_labevents
        GROUP BY
          hadm_id
      )
    SELECT
      bc.hadm_id,
      bc.is_aki_patient,
      COALESCE(cc.instability_score, 0) AS instability_score,
      COALESCE(tc.total_lab_tests, 0) AS total_lab_tests,
      DATETIME_DIFF(bc.dischtime, bc.admittime, DAY) AS los_days,
      bc.hospital_expire_flag
    FROM
      base_cohorts AS bc
      LEFT JOIN critical_counts AS cc ON bc.hadm_id = cc.hadm_id
      LEFT JOIN total_counts AS tc ON bc.hadm_id = tc.hadm_id
  ),
  ranked_scores AS (
    SELECT
      hadm_id,
      is_aki_patient,
      instability_score,
      total_lab_tests,
      los_days,
      hospital_expire_flag,
      PERCENT_RANK() OVER (
        PARTITION BY
          is_aki_patient
        ORDER BY
          instability_score
      ) AS percentile_rank_in_group
    FROM
      patient_level_summary
  )
SELECT
  CASE
    WHEN is_aki_patient = 1 THEN 'AKI Cohort (Male, 47-57)'
    ELSE 'Control Cohort (Male, 47-57)'
  END AS cohort,
  COUNT(DISTINCT hadm_id) AS number_of_patients,
  AVG(instability_score) AS avg_instability_score,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(25)] AS p25_instability_score,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(50)] AS p50_instability_score,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(75)] AS p75_instability_score,
  SUM(instability_score) AS total_critical_events_in_72h,
  SUM(total_lab_tests) AS total_lab_tests_in_72h,
  SAFE_DIVIDE(SUM(instability_score), SUM(total_lab_tests)) AS critical_event_frequency,
  AVG(los_days) AS avg_length_of_stay_days,
  AVG(hospital_expire_flag) AS in_hospital_mortality_rate
FROM
  ranked_scores
GROUP BY
  is_aki_patient
ORDER BY
  is_aki_patient DESC;
