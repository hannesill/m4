WITH
cohort_base AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    i.stay_id,
    i.intime,
    i.outtime,
    DATETIME_DIFF(i.outtime, i.intime, HOUR) / 24.0 AS icu_los_days,
    a.hospital_expire_flag,
    DATETIME_ADD(i.intime, INTERVAL 24 HOUR) AS end_time_24h
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS i ON a.hadm_id = i.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 85 AND 95
),
arf_diagnoses AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND icd_code IN ('51881', '51882', '51884'))
    OR
    (icd_version = 10 AND SUBSTR(icd_code, 1, 4) IN ('J960', 'J962'))
),
cohort_final AS (
  SELECT
    cb.stay_id,
    cb.intime,
    cb.end_time_24h,
    cb.icu_los_days,
    cb.hospital_expire_flag
  FROM cohort_base AS cb
  INNER JOIN arf_diagnoses AS ad
    ON cb.hadm_id = ad.hadm_id
),
vitals_raw AS (
  SELECT
    stay_id,
    charttime,
    itemid,
    valuenum
  FROM `physionet-data.mimiciv_3_1_icu.chartevents`
  WHERE
    stay_id IN (SELECT stay_id FROM cohort_final)
    AND itemid IN (
      220045,
      220179,
      220050,
      220228,
      220052,
      220210,
      223762,
      220277
    )
    AND valuenum IS NOT NULL
),
abnormal_events AS (
  SELECT
    v.stay_id,
    CASE
      WHEN v.itemid = 220045 AND (v.valuenum < 60 OR v.valuenum > 100) THEN 1
      WHEN v.itemid IN (220179, 220050) AND (v.valuenum < 90 OR v.valuenum > 160) THEN 1
      WHEN v.itemid IN (220228, 220052) AND v.valuenum < 65 THEN 1
      WHEN v.itemid = 220210 AND (v.valuenum < 12 OR v.valuenum > 25) THEN 1
      WHEN v.itemid = 223762 AND (v.valuenum < 36.0 OR v.valuenum > 38.3) THEN 1
      WHEN v.itemid = 220277 AND v.valuenum < 92 THEN 1
      ELSE 0
    END AS is_abnormal
  FROM vitals_raw AS v
  INNER JOIN cohort_final AS c
    ON v.stay_id = c.stay_id
  WHERE v.charttime BETWEEN c.intime AND c.end_time_24h
),
instability_scores AS (
  SELECT
    stay_id,
    SUM(is_abnormal) AS instability_score
  FROM abnormal_events
  GROUP BY stay_id
),
final_scores_with_quartiles AS (
  SELECT
    c.stay_id,
    c.icu_los_days,
    c.hospital_expire_flag,
    COALESCE(s.instability_score, 0) AS instability_score,
    NTILE(4) OVER (ORDER BY COALESCE(s.instability_score, 0) DESC) AS instability_quartile
  FROM cohort_final AS c
  LEFT JOIN instability_scores AS s
    ON c.stay_id = s.stay_id
),
aggregated_outcomes AS (
  SELECT
    'Percentile Rank for Score of 85' AS metric,
    ROUND((COUNTIF(instability_score < 85) * 100.0) / COUNT(*), 2) AS value,
    '%' AS unit,
    'Percentile rank of a hypothetical instability score of 85 within the cohort.' AS description,
    1 AS result_order
  FROM final_scores_with_quartiles
  UNION ALL
  SELECT
    'Avg ICU LOS (Most Unstable Quartile)' AS metric,
    ROUND(AVG(IF(instability_quartile = 1, icu_los_days, NULL)), 2) AS value,
    'Days' AS unit,
    'Average ICU Length of Stay for the most unstable quartile (top 25%).' AS description,
    2 AS result_order
  FROM final_scores_with_quartiles
  UNION ALL
  SELECT
    'Mortality Rate (Most Unstable Quartile)' AS metric,
    ROUND(AVG(IF(instability_quartile = 1, CAST(hospital_expire_flag AS INT64), NULL)) * 100.0, 2) AS value,
    '%' AS unit,
    'In-hospital mortality rate for the most unstable quartile (top 25%).' AS description,
    3 AS result_order
  FROM final_scores_with_quartiles
  UNION ALL
  SELECT
    'Patient Count (Most Unstable Quartile)' AS metric,
    CAST(COUNTIF(instability_quartile = 1) AS FLOAT64) AS value,
    'Patients' AS unit,
    'Number of patients in the most unstable quartile.' AS description,
    4 AS result_order
  FROM final_scores_with_quartiles
  UNION ALL
  SELECT
    'Patient Count (Total Cohort)' AS metric,
    CAST(COUNT(*) AS FLOAT64) AS value,
    'Patients' AS unit,
    'Total number of patients in the Male, 85-95, ARF cohort.' AS description,
    5 AS result_order
  FROM final_scores_with_quartiles
)
SELECT
  metric,
  value,
  unit,
  description
FROM aggregated_outcomes
ORDER BY result_order;
