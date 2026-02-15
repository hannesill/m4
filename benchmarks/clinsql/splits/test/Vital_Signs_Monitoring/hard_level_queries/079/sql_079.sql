WITH
  demographic_cohort AS (
    SELECT
      icu.stay_id,
      icu.intime
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    WHERE
      pat.gender = 'M'
      AND pat.anchor_age BETWEEN 81 AND 91
  ),
  hfnc_cohort AS (
    SELECT DISTINCT stay_id
    FROM `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
      stay_id IN (SELECT stay_id FROM demographic_cohort)
      AND itemid = 227287 AND valuenum > 0
      AND charttime <= (
        SELECT DATETIME_ADD(dc.intime, INTERVAL 48 HOUR)
        FROM demographic_cohort AS dc
        WHERE dc.stay_id = `physionet-data.mimiciv_3_1_icu.chartevents`.stay_id
      )
  ),
  vitals_filtered AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.valuenum
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN demographic_cohort AS dc ON ce.stay_id = dc.stay_id
    WHERE
      ce.stay_id IN (SELECT stay_id FROM hfnc_cohort)
      AND ce.charttime BETWEEN dc.intime AND DATETIME_ADD(dc.intime, INTERVAL 48 HOUR)
      AND ce.itemid IN (
        220045,
        220179,
        220210,
        220277,
        223762
      )
      AND ce.valuenum IS NOT NULL
  ),
  abnormal_events AS (
    SELECT
      stay_id,
      CASE
        WHEN itemid = 220045 AND (valuenum < 50 OR valuenum > 120) THEN 1
        WHEN itemid = 220179 AND (valuenum < 90 OR valuenum > 180) THEN 1
        WHEN itemid = 220210 AND (valuenum < 8 OR valuenum > 25) THEN 1
        WHEN itemid = 220277 AND valuenum < 90 THEN 1
        WHEN itemid = 223762 AND (valuenum < 36.0 OR valuenum > 38.5) THEN 1
        ELSE 0
      END AS is_abnormal
    FROM vitals_filtered
  ),
  instability_scores AS (
    SELECT
      ae.stay_id,
      SUM(ae.is_abnormal) AS composite_instability_score,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours,
      adm.hospital_expire_flag
    FROM abnormal_events AS ae
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON ae.stay_id = icu.stay_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    GROUP BY
      ae.stay_id,
      icu.outtime,
      icu.intime,
      adm.hospital_expire_flag
  ),
  final_stats AS (
    SELECT
      stay_id,
      composite_instability_score,
      icu_los_hours,
      hospital_expire_flag,
      CUME_DIST() OVER (ORDER BY composite_instability_score) AS percentile_rank,
      NTILE(10) OVER (ORDER BY composite_instability_score DESC) AS score_decile
    FROM instability_scores
  )
SELECT
  'Percentile Rank for Score 85' AS metric,
  MAX(CASE WHEN composite_instability_score <= 85 THEN percentile_rank ELSE 0 END) * 100 AS value1,
  NULL AS value2,
  'The percentile rank of a composite instability score of 85 within the cohort.' AS description
FROM final_stats
UNION ALL
SELECT
  'Top Decile Outcomes' AS metric,
  AVG(icu_los_hours / 24.0) AS value1,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS value2,
  'Avg ICU LOS (days) and Mortality (%) for patients in the top 10% of instability scores.' AS description
FROM final_stats
WHERE score_decile = 1;
