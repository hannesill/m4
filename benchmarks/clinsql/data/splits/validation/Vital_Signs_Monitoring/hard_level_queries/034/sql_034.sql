WITH
  icd_shock AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code IN ('R578', '78559')
  ),
  cohort_stays AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      adm.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    WHERE icu.hadm_id IN (SELECT hadm_id FROM icd_shock)
      AND pat.gender = 'F'
      AND (pat.anchor_age + DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 60 AND 70
  ),
  instability_and_episodes AS (
    SELECT
      cs.stay_id,
      cs.hospital_expire_flag,
      DATETIME_DIFF(cs.outtime, cs.intime, HOUR) AS icu_los_hours,
      SAFE_DIVIDE(
        STDDEV(CASE WHEN ce.itemid = 220045 THEN ce.valuenum END),
        AVG(CASE WHEN ce.itemid = 220045 THEN ce.valuenum END)
      ) AS hr_cv,
      SAFE_DIVIDE(
        STDDEV(CASE WHEN ce.itemid IN (220181, 225312) THEN ce.valuenum END),
        AVG(CASE WHEN ce.itemid IN (220181, 225312) THEN ce.valuenum END)
      ) AS map_cv,
      SAFE_DIVIDE(
        STDDEV(CASE WHEN ce.itemid = 220210 THEN ce.valuenum END),
        AVG(CASE WHEN ce.itemid = 220210 THEN ce.valuenum END)
      ) AS rr_cv,
      COUNTIF(ce.itemid IN (220181, 225312) AND ce.valuenum < 65) AS hypotension_episodes,
      COUNTIF(ce.itemid = 220045 AND ce.valuenum > 100) AS tachycardia_episodes
    FROM cohort_stays AS cs
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON cs.stay_id = ce.stay_id
      AND DATETIME_DIFF(ce.charttime, cs.intime, HOUR) BETWEEN 0 AND 48
      AND ce.itemid IN (
        220045,
        220181,
        225312,
        220210
      )
      AND ce.valuenum IS NOT NULL AND ce.valuenum > 0
    GROUP BY
      cs.stay_id,
      cs.hospital_expire_flag,
      cs.outtime,
      cs.intime
  ),
  ranked_scores AS (
    SELECT
      *,
      (COALESCE(hr_cv, 0) + COALESCE(map_cv, 0) + COALESCE(rr_cv, 0)) AS instability_score,
      NTILE(10) OVER (ORDER BY (COALESCE(hr_cv, 0) + COALESCE(map_cv, 0) + COALESCE(rr_cv, 0)) DESC) AS instability_decile
    FROM instability_and_episodes
  ),
  final_stats AS (
    SELECT
      *,
      PERCENTILE_CONT(instability_score, 0.95) OVER () AS p95_instability_score
    FROM ranked_scores
  )
SELECT
  'Top Decile (Highest Instability)' AS comparison_group,
  MIN(p95_instability_score) AS cohort_p95_instability_score,
  COUNT(stay_id) AS num_patients,
  AVG(instability_score) AS avg_instability_score,
  AVG(hypotension_episodes) AS avg_hypotension_episodes,
  AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
  AVG(icu_los_hours / 24.0) AS avg_icu_los_days,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
FROM final_stats
WHERE instability_decile = 1

UNION ALL

SELECT
  'Entire Cohort (Female, 60-70, Mixed Shock)' AS comparison_group,
  MIN(p95_instability_score) AS cohort_p95_instability_score,
  COUNT(stay_id) AS num_patients,
  AVG(instability_score) AS avg_instability_score,
  AVG(hypotension_episodes) AS avg_hypotension_episodes,
  AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
  AVG(icu_los_hours / 24.0) AS avg_icu_los_days,
  AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
FROM final_stats;
