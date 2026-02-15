WITH
  rrt_stays AS (
    SELECT DISTINCT
      stay_id
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
      itemid IN (
        225809,
        224149,
        225977,
        224144,
        224145
      )
  ),
  cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      i.stay_id,
      p.gender,
      p.anchor_age,
      i.intime,
      i.outtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(i.outtime, i.intime, HOUR) / 24.0 AS icu_los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS i
      ON a.hadm_id = i.hadm_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 88 AND 98
      AND i.stay_id IN (
        SELECT
          stay_id
        FROM
          rrt_stays
      )
  ),
  vitals_abnormal AS (
    SELECT
      ce.stay_id,
      CASE
        WHEN ce.itemid = 220045 AND (ce.valuenum > 120 OR ce.valuenum < 50) THEN 1
        WHEN ce.itemid = 220179 AND (ce.valuenum > 180 OR ce.valuenum < 90) THEN 1
        WHEN ce.itemid = 220052 AND ce.valuenum < 65 THEN 1
        WHEN ce.itemid = 220210 AND (ce.valuenum > 25 OR ce.valuenum < 10) THEN 1
        WHEN ce.itemid = 223762 AND (ce.valuenum > 38.5 OR ce.valuenum < 36.0) THEN 1
        WHEN ce.itemid = 220277 AND ce.valuenum < 90 THEN 1
        ELSE 0
      END AS is_abnormal
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      cohort AS ch
      ON ce.stay_id = ch.stay_id
    WHERE
      ce.charttime BETWEEN ch.intime AND DATETIME_ADD(ch.intime, INTERVAL 72 HOUR)
      AND ce.itemid IN (
        220045,
        220179,
        220052,
        220210,
        223762,
        220277
      )
      AND ce.valuenum IS NOT NULL
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
  ranked_cohort AS (
    SELECT
      c.stay_id,
      c.icu_los_days,
      c.hospital_expire_flag,
      s.instability_score,
      CUME_DIST() OVER (
        ORDER BY
          s.instability_score
      ) AS percentile_rank,
      NTILE(4) OVER (
        ORDER BY
          s.instability_score DESC
      ) AS score_quartile
    FROM
      instability_scores AS s
    INNER JOIN
      cohort AS c
      ON s.stay_id = c.stay_id
  ),
  target_percentile AS (
    SELECT
      'Percentile Rank for Score 85' AS metric,
      ROUND(
        MAX(
          CASE
            WHEN instability_score <= 85 THEN percentile_rank
            ELSE 0
          END
        ) * 100,
        2
      ) AS value,
      '%' AS unit,
      1 AS sort_order
    FROM
      ranked_cohort
  ),
  top_quartile_stats AS (
    SELECT
      'Avg ICU LOS (Top Quartile)' AS metric,
      ROUND(AVG(icu_los_days), 2) AS value,
      'days' AS unit,
      2 AS sort_order
    FROM
      ranked_cohort
    WHERE
      score_quartile = 1
    UNION ALL
    SELECT
      'Mortality Rate (Top Quartile)' AS metric,
      ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS value,
      '%' AS unit,
      3 AS sort_order
    FROM
      ranked_cohort
    WHERE
      score_quartile = 1
  ),
  combined_results AS (
    SELECT
      metric,
      value,
      unit,
      sort_order
    FROM
      target_percentile
    UNION ALL
    SELECT
      metric,
      value,
      unit,
      sort_order
    FROM
      top_quartile_stats
  )
SELECT
  metric,
  value,
  unit
FROM
  combined_results
ORDER BY
  sort_order;
