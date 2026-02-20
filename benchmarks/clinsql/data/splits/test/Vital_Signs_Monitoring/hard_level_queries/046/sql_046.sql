WITH icd_stroke AS (
  SELECT DISTINCT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (
      icd_version = 9
      AND SUBSTR(icd_code, 1, 3) IN ('433', '434')
    )
    OR (
      icd_version = 10
      AND SUBSTR(icd_code, 1, 3) = 'I63'
    )
),
cohort_stays AS (
  SELECT
    icu.stay_id,
    icu.intime,
    icu.outtime,
    adm.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON icu.subject_id = pat.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
    INNER JOIN icd_stroke ON icu.hadm_id = icd_stroke.hadm_id
  WHERE
    pat.gender = 'M'
    AND pat.anchor_age BETWEEN 84 AND 94
),
vitals_raw AS (
  SELECT
    stay_id,
    charttime,
    itemid,
    valuenum
  FROM
    `physionet-data.mimiciv_3_1_icu.chartevents`
  WHERE
    itemid IN (
      220045,
      220179,
      220052,
      220210,
      220277,
      223762
    )
    AND stay_id IN (
      SELECT
        stay_id
      FROM
        cohort_stays
    )
),
abnormal_events AS (
  SELECT
    vs.stay_id,
    CASE
      WHEN vs.itemid = 220045 AND (vs.valuenum < 50 OR vs.valuenum > 120) THEN 1
      WHEN vs.itemid = 220179 AND (vs.valuenum < 90 OR vs.valuenum > 160) THEN 1
      WHEN vs.itemid = 220052 AND vs.valuenum < 65 THEN 1
      WHEN vs.itemid = 220210 AND (vs.valuenum < 10 OR vs.valuenum > 25) THEN 1
      WHEN vs.itemid = 220277 AND vs.valuenum < 92 THEN 1
      WHEN vs.itemid = 223762 AND (vs.valuenum < 36 OR vs.valuenum > 38.5) THEN 1
      ELSE 0
    END AS is_abnormal
  FROM
    vitals_raw AS vs
    INNER JOIN cohort_stays AS cs ON vs.stay_id = cs.stay_id
  WHERE
    DATETIME_DIFF(vs.charttime, cs.intime, HOUR) BETWEEN 0 AND 72
    AND vs.valuenum IS NOT NULL
),
instability_scores AS (
  SELECT
    stay_id,
    SUM(is_abnormal) AS instability_score
  FROM
    abnormal_events
  GROUP BY
    stay_id
),
ranked_scores AS (
  SELECT
    sc.stay_id,
    sc.instability_score,
    cs.hospital_expire_flag,
    DATETIME_DIFF(cs.outtime, cs.intime, HOUR) / 24.0 AS icu_los_days,
    NTILE(4) OVER (
      ORDER BY
        sc.instability_score DESC
    ) AS instability_quartile
  FROM
    instability_scores AS sc
    INNER JOIN cohort_stays AS cs ON sc.stay_id = cs.stay_id
),
percentile_for_target_score AS (
  SELECT
    SAFE_DIVIDE(
      (
        COUNTIF(instability_score < 80) + (0.5 * COUNTIF(instability_score = 80))
      ),
      COUNT(instability_score)
    ) * 100 AS percentile_rank_of_score_80
  FROM
    instability_scores
),
top_quartile_stats AS (
  SELECT
    AVG(icu_los_days) AS avg_los_top_quartile,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_top_quartile
  FROM
    ranked_scores
  WHERE
    instability_quartile = 1
)
SELECT
  tps.percentile_rank_of_score_80,
  tqs.avg_los_top_quartile,
  tqs.mortality_rate_top_quartile
FROM
  percentile_for_target_score AS tps
  CROSS JOIN top_quartile_stats AS tqs;
