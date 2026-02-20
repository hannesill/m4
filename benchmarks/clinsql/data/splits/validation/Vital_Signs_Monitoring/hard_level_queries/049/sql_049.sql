WITH
  sepsis_cohort AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE 'A40%' OR icd_code LIKE 'A41%' OR
      icd_code LIKE 'R65.2%' OR
      icd_code LIKE '038%' OR icd_code = '99591' OR icd_code = '99592'
  ),
  icu_cohort AS (
    SELECT
      icu.stay_id,
      icu.intime,
      icu.outtime,
      adm.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    INNER JOIN sepsis_cohort AS sep
      ON icu.hadm_id = sep.hadm_id
    WHERE
      pat.gender = 'M'
      AND pat.anchor_age BETWEEN 78 AND 88
  ),
  vitals_first_24h AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.valuenum
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN icu_cohort AS icu
      ON ce.stay_id = icu.stay_id
    WHERE
      ce.charttime >= icu.intime AND ce.charttime <= DATETIME_ADD(icu.intime, INTERVAL 24 HOUR)
      AND ce.valuenum IS NOT NULL
      AND ce.itemid IN (
        220045, 211,
        220179, 220050,
        220181, 220052,
        220210, 219,
        223762, 676,
        220277, 646
      )
  ),
  abnormal_events AS (
    SELECT
      stay_id,
      CASE
        WHEN itemid IN (220045, 211) AND (valuenum < 60 OR valuenum > 100) THEN 1
        WHEN itemid IN (220179, 220050) AND (valuenum < 90 OR valuenum > 160) THEN 1
        WHEN itemid IN (220181, 220052) AND valuenum < 65 THEN 1
        WHEN itemid IN (220210, 219) AND (valuenum < 12 OR valuenum > 25) THEN 1
        WHEN itemid IN (223762, 676) AND (valuenum < 36.0 OR valuenum > 38.3) THEN 1
        WHEN itemid IN (220277, 646) AND valuenum < 92 THEN 1
        ELSE 0
      END AS is_abnormal
    FROM vitals_first_24h
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(is_abnormal) AS instability_score
    FROM abnormal_events
    GROUP BY stay_id
  ),
  cohort_stats AS (
    SELECT
      icu.stay_id,
      icu.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days,
      COALESCE(sc.instability_score, 0) AS instability_score,
      NTILE(4) OVER (ORDER BY COALESCE(sc.instability_score, 0)) AS instability_quartile
    FROM icu_cohort AS icu
    LEFT JOIN instability_scores AS sc
      ON icu.stay_id = sc.stay_id
  ),
  percentile_calc AS (
    SELECT
      SAFE_DIVIDE(
        (SELECT COUNT(*) FROM cohort_stats WHERE instability_score < 85),
        (SELECT COUNT(*) FROM cohort_stats)
      ) * 100 AS percentile_rank_of_score_85
  ),
  quartile_outcomes AS (
    SELECT
      AVG(icu_los_days) AS q4_avg_icu_los_days,
      AVG(CAST(hospital_expire_flag AS INT64)) * 100 AS q4_mortality_rate_percent
    FROM cohort_stats
    WHERE instability_quartile = 4
  )
SELECT
  p.percentile_rank_of_score_85,
  q.q4_avg_icu_los_days,
  q.q4_mortality_rate_percent
FROM percentile_calc AS p, quartile_outcomes AS q;
