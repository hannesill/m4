WITH
pneumonia_cohort AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '480' AND '486')
    OR
    (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
),
target_cohort AS (
  SELECT
    icu.subject_id,
    icu.hadm_id,
    icu.stay_id,
    icu.intime,
    icu.outtime,
    adm.hospital_expire_flag,
    DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days
  FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON icu.subject_id = pat.subject_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    ON icu.hadm_id = adm.hadm_id
  INNER JOIN pneumonia_cohort AS pna
    ON icu.hadm_id = pna.hadm_id
  WHERE
    pat.gender = 'F'
    AND pat.anchor_age BETWEEN 55 AND 65
),
vitals_first_24h AS (
  SELECT
    ce.stay_id,
    ce.itemid,
    ce.valuenum
  FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
  INNER JOIN target_cohort AS cohort
    ON ce.stay_id = cohort.stay_id
  WHERE
    ce.charttime BETWEEN cohort.intime AND DATETIME_ADD(cohort.intime, INTERVAL 24 HOUR)
    AND ce.itemid IN (
        220045,
        220179,
        220050,
        220210,
        223762,
        220277
    )
    AND ce.valuenum IS NOT NULL
),
abnormal_events AS (
  SELECT
    stay_id,
    CASE
      WHEN itemid = 220045 AND (valuenum < 50 OR valuenum > 120) THEN 1
      WHEN itemid IN (220179, 220050) AND (valuenum < 90 OR valuenum > 180) THEN 1
      WHEN itemid = 220210 AND (valuenum < 8 OR valuenum > 25) THEN 1
      WHEN itemid = 223762 AND (valuenum < 36.0 OR valuenum > 38.5) THEN 1
      WHEN itemid = 220277 AND valuenum < 90 THEN 1
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
ranked_scores AS (
  SELECT
    sc.stay_id,
    sc.instability_score,
    cohort.icu_los_days,
    cohort.hospital_expire_flag,
    NTILE(10) OVER(ORDER BY sc.instability_score DESC) AS instability_decile
  FROM instability_scores AS sc
  INNER JOIN target_cohort AS cohort
    ON sc.stay_id = cohort.stay_id
),
target_score_percentile AS (
  SELECT
    100.0 * (SELECT COUNT(*) FROM instability_scores WHERE instability_score < 60)
    /
    (SELECT COUNT(*) FROM instability_scores) AS percentile_rank_of_score_60
),
unstable_decile_outcomes AS (
  SELECT
    AVG(icu_los_days) AS most_unstable_decile_avg_los,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS most_unstable_decile_mortality_pct
  FROM ranked_scores
  WHERE instability_decile = 1
)
SELECT
  'Female, Age 55-65, with Pneumonia' AS cohort_description,
  60 AS target_instability_score,
  ROUND(tp.percentile_rank_of_score_60, 2) AS percentile_rank_of_target_score,
  ROUND(uo.most_unstable_decile_avg_los, 1) AS most_unstable_decile_avg_los_days,
  ROUND(uo.most_unstable_decile_mortality_pct, 2) AS most_unstable_decile_mortality_rate_pct
FROM target_score_percentile AS tp
CROSS JOIN unstable_decile_outcomes AS uo;
