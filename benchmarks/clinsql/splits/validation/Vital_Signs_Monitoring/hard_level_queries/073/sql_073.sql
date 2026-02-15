WITH
  ich_diagnoses AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432'))
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62'))
  ),
  cohort_stays AS (
    SELECT
      p.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      adm.hospital_expire_flag
    FROM (
        SELECT *, ROW_NUMBER() OVER(PARTITION BY hadm_id ORDER BY intime) as rn
        FROM `physionet-data.mimiciv_3_1_icu.icustays`
    ) AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON icu.subject_id = p.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    WHERE icu.rn = 1
      AND icu.hadm_id IN (SELECT hadm_id FROM ich_diagnoses)
      AND p.gender = 'F'
      AND p.anchor_age BETWEEN 47 AND 57
  ),
  vitals_first_72h AS (
    SELECT
      ch.stay_id,
      ch.itemid,
      ch.valuenum
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ch
    INNER JOIN cohort_stays AS cs
      ON ch.stay_id = cs.stay_id
    WHERE
      ch.charttime BETWEEN cs.intime AND DATETIME_ADD(cs.intime, INTERVAL 72 HOUR)
      AND ch.itemid IN (
        220045,
        220179,
        220050,
        220210,
        220277,
        223761
      )
      AND ch.valuenum IS NOT NULL AND ch.valuenum > 0
  ),
  abnormal_events AS (
    SELECT
      stay_id,
      CASE
        WHEN itemid = 220045 AND (valuenum < 60 OR valuenum > 100) THEN 1
        WHEN itemid IN (220179, 220050) AND (valuenum < 90 OR valuenum > 140) THEN 1
        WHEN itemid = 220210 AND (valuenum < 12 OR valuenum > 20) THEN 1
        WHEN itemid = 220277 AND valuenum < 94 THEN 1
        WHEN itemid = 223761 AND (valuenum < 96.8 OR valuenum > 100.4) THEN 1
        ELSE 0
      END AS is_abnormal
    FROM vitals_first_72h
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(is_abnormal) AS instability_score
    FROM abnormal_events
    GROUP BY stay_id
  ),
  ranked_scores AS (
    SELECT
      sc.stay_id,
      sc.instability_score,
      cs.hospital_expire_flag,
      DATETIME_DIFF(cs.outtime, cs.intime, DAY) AS icu_los_days,
      PERCENT_RANK() OVER (ORDER BY sc.instability_score) AS percentile_rank,
      NTILE(10) OVER (ORDER BY sc.instability_score) AS decile
    FROM instability_scores AS sc
    INNER JOIN cohort_stays AS cs
      ON sc.stay_id = cs.stay_id
  )
SELECT
  (
    SELECT SAFE_DIVIDE(COUNTIF(instability_score < 75), (COUNT(*) - 1))
    FROM instability_scores
  ) AS percentile_rank_of_score_75,
  (
    SELECT AVG(icu_los_days)
    FROM ranked_scores WHERE decile = 10
  ) AS top_decile_avg_icu_los_days,
  (
    SELECT AVG(CAST(hospital_expire_flag AS INT64))
    FROM ranked_scores WHERE decile = 10
  ) AS top_decile_mortality_rate,
  (
    SELECT COUNT(DISTINCT stay_id)
    FROM cohort_stays
  ) AS cohort_patient_count,
  (
    SELECT AVG(instability_score)
    FROM instability_scores
  ) AS cohort_avg_instability_score;
