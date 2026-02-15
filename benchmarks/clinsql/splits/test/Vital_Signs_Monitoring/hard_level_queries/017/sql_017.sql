WITH
  icustay_details AS (
    SELECT
      icu.stay_id,
      icu.hadm_id,
      icu.subject_id,
      icu.intime,
      icu.outtime,
      pat.gender,
      (
        EXTRACT(YEAR FROM icu.intime) - pat.anchor_year + pat.anchor_age
      ) AS age_at_icu_admission,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON icu.subject_id = pat.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
    WHERE
      (
        EXTRACT(YEAR FROM icu.intime) - pat.anchor_year + pat.anchor_age
      ) BETWEEN 83 AND 93
  ),
  asthma_cohort_stays AS (
    SELECT DISTINCT
      icd.stay_id
    FROM
      icustay_details AS icd
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag ON icd.hadm_id = diag.hadm_id
    WHERE
      icd.gender = 'F'
      AND diag.icd_code IN (
        '49301',
        '49311',
        '49321',
        '49391',
        'J4521',
        'J4531',
        'J4541',
        'J4551',
        'J45901'
      )
  ),
  vitals_first_72h AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      INNER JOIN icustay_details AS icu ON ce.stay_id = icu.stay_id
    WHERE
      ce.itemid IN (
        220045,
        220179,
        220210,
        223762,
        220277
      )
      AND ce.valuenum IS NOT NULL
      AND ce.charttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
  ),
  vitals_abnormal AS (
    SELECT
      stay_id,
      CASE
        WHEN itemid = 220045 AND (valuenum > 120 OR valuenum < 50) THEN 1
        WHEN itemid = 220179 AND (valuenum > 160 OR valuenum < 90) THEN 1
        WHEN itemid = 220210 AND (valuenum > 25 OR valuenum < 10) THEN 1
        WHEN itemid = 223762 AND (valuenum > 38.5 OR valuenum < 36.0) THEN 1
        WHEN itemid = 220277 AND valuenum < 90 THEN 1
        ELSE 0
      END AS is_abnormal
    FROM
      vitals_first_72h
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(is_abnormal) AS instability_score
    FROM
      vitals_abnormal
    GROUP BY
      stay_id
  ),
  cohort_data AS (
    SELECT
      icu.stay_id,
      CASE
        WHEN ast.stay_id IS NOT NULL THEN 'Asthma_Female_83_93'
        ELSE 'All_ICU_Age_Matched_83_93'
      END AS cohort_group,
      COALESCE(sc.instability_score, 0) AS instability_score,
      icu.icu_los_days,
      icu.hospital_expire_flag
    FROM
      icustay_details AS icu
      LEFT JOIN asthma_cohort_stays AS ast ON icu.stay_id = ast.stay_id
      LEFT JOIN instability_scores AS sc ON icu.stay_id = sc.stay_id
  )
SELECT
  cohort_group,
  COUNT(DISTINCT stay_id) AS num_stays,
  AVG(instability_score) AS avg_instability_score,
  STDDEV(instability_score) AS stddev_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(25)] AS p25_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(50)] AS p50_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(75)] AS p75_instability_score,
  APPROX_QUANTILES(instability_score, 100)[OFFSET(95)] AS p95_instability_score,
  AVG(icu_los_days) AS avg_icu_los_days,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent
FROM
  cohort_data
GROUP BY
  cohort_group
ORDER BY
  cohort_group;
