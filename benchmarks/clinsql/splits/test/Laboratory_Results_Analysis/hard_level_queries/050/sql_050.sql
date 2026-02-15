WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days,
      p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 40 AND 50
  ),
  ards_cohort AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code IN ('J80', '51882')
  ),
  labs_first_72h AS (
    SELECT
      bc.hadm_id,
      le.itemid,
      le.valuenum,
      CASE
        WHEN le.itemid IN (50983, 50824) THEN 'Sodium'
        WHEN le.itemid IN (50971, 50822) THEN 'Potassium'
        WHEN le.itemid IN (50912, 50813) THEN 'Creatinine'
        WHEN le.itemid IN (50813) THEN 'Lactate'
        WHEN le.itemid IN (51301, 51300) THEN 'WBC'
        WHEN le.itemid IN (51265) THEN 'Platelets'
        WHEN le.itemid IN (50882, 50803) THEN 'Bicarbonate'
        WHEN le.itemid IN (50868, 50802) THEN 'Anion Gap'
      END AS lab_name
    FROM
      base_cohort AS bc
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON bc.hadm_id = le.hadm_id
    WHERE
      le.charttime BETWEEN bc.admittime AND DATETIME_ADD(bc.admittime, INTERVAL 72 HOUR)
      AND le.valuenum IS NOT NULL
      AND le.itemid IN (
        50983, 50824,
        50971, 50822,
        50912, 50813,
        50813,
        51301, 51300,
        51265,
        50882, 50803,
        50868, 50802
      )
  ),
  abnormal_flags AS (
    SELECT
      hadm_id,
      lab_name,
      CASE
        WHEN lab_name = 'Sodium' AND (valuenum < 135 OR valuenum > 145) THEN 1
        WHEN lab_name = 'Potassium' AND (valuenum < 3.5 OR valuenum > 5.2) THEN 1
        WHEN lab_name = 'Creatinine' AND (valuenum > 1.2) THEN 1
        WHEN lab_name = 'Lactate' AND (valuenum > 2.0) THEN 1
        WHEN lab_name = 'WBC' AND (valuenum < 4.0 OR valuenum > 11.0) THEN 1
        WHEN lab_name = 'Platelets' AND (valuenum < 150) THEN 1
        WHEN lab_name = 'Bicarbonate' AND (valuenum < 22 OR valuenum > 29) THEN 1
        WHEN lab_name = 'Anion Gap' AND (valuenum > 12) THEN 1
        ELSE 0
      END AS is_abnormal,
      CASE
        WHEN lab_name = 'Sodium' AND (valuenum < 125 OR valuenum > 155) THEN 1
        WHEN lab_name = 'Potassium' AND (valuenum < 2.5 OR valuenum > 6.5) THEN 1
        WHEN lab_name = 'Creatinine' AND (valuenum > 3.5) THEN 1
        WHEN lab_name = 'Lactate' AND (valuenum > 4.0) THEN 1
        WHEN lab_name = 'WBC' AND (valuenum < 2.0 OR valuenum > 30.0) THEN 1
        WHEN lab_name = 'Platelets' AND (valuenum < 20) THEN 1
        WHEN lab_name = 'Bicarbonate' AND (valuenum < 15 OR valuenum > 40) THEN 1
        ELSE 0
      END AS is_critical
    FROM
      labs_first_72h
  ),
  patient_scores AS (
    SELECT
      bc.hadm_id,
      bc.hospital_expire_flag,
      bc.los_days,
      CASE
        WHEN ac.hadm_id IS NOT NULL THEN TRUE
        ELSE FALSE
      END AS is_ards_patient,
      COUNT(DISTINCT CASE WHEN af.is_abnormal = 1 THEN af.lab_name END) AS instability_score,
      SUM(af.is_critical) AS critical_event_count
    FROM
      base_cohort AS bc
      LEFT JOIN ards_cohort AS ac
      ON bc.hadm_id = ac.hadm_id
      LEFT JOIN abnormal_flags AS af
      ON bc.hadm_id = af.hadm_id
    GROUP BY
      bc.hadm_id,
      bc.hospital_expire_flag,
      bc.los_days,
      is_ards_patient
  ),
  ards_score_percentile AS (
    SELECT DISTINCT
      PERCENTILE_CONT(instability_score, 0.75) OVER () AS p75_instability_score
    FROM
      patient_scores
    WHERE
      is_ards_patient = TRUE
  )
SELECT
  (SELECT p75_instability_score FROM ards_score_percentile LIMIT 1) AS ards_75th_percentile_score,
  patient_category,
  COUNT(hadm_id) AS number_of_patients,
  AVG(instability_score) AS avg_instability_score,
  AVG(los_days) AS avg_length_of_stay_days,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate,
  SAFE_DIVIDE(SUM(critical_event_count), COUNT(hadm_id)) AS avg_critical_events_per_patient
FROM (
  SELECT
    ps.*,
    CASE
      WHEN ps.is_ards_patient = TRUE AND ps.instability_score >= p.p75_instability_score
      THEN 'Top Tier ARDS (>=75th Pct)'
      WHEN ps.is_ards_patient = TRUE AND ps.instability_score < p.p75_instability_score
      THEN 'Lower Tier ARDS (<75th Pct)'
      ELSE 'Control Group (Non-ARDS)'
    END AS patient_category
  FROM
    patient_scores AS ps,
    ards_score_percentile AS p
)
GROUP BY
  patient_category
ORDER BY
  CASE
    WHEN patient_category = 'Top Tier ARDS (>=75th Pct)' THEN 1
    WHEN patient_category = 'Control Group (Non-ARDS)' THEN 2
    ELSE 3
  END;
