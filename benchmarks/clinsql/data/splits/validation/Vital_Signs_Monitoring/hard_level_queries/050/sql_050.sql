WITH
  cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      i.stay_id,
      i.intime,
      i.outtime,
      DATETIME_DIFF(i.outtime, i.intime, DAY) AS icu_los_days,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS i ON a.hadm_id = i.hadm_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM i.intime) - p.anchor_year + p.anchor_age) BETWEEN 52 AND 62
  ),
  rrt_stays AS (
    SELECT DISTINCT
      c.stay_id
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` c
    WHERE
      c.stay_id IN (SELECT stay_id FROM cohort)
      AND c.itemid IN (
        225802,
        225803,
        225805,
        224149,
        224150,
        225441
      )
  ),
  vitals_raw AS (
    SELECT
      c.stay_id,
      c.itemid,
      c.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS c
    INNER JOIN cohort AS i ON c.stay_id = i.stay_id
    WHERE
      c.stay_id IN (SELECT stay_id FROM rrt_stays)
      AND c.charttime BETWEEN i.intime AND DATETIME_ADD(i.intime, INTERVAL 72 HOUR)
      AND c.itemid IN (
        220045,
        220179,
        220052,
        220210,
        220277
      )
      AND c.valuenum IS NOT NULL AND c.valuenum > 0
  ),
  vitals_stddev AS (
    SELECT
      stay_id,
      itemid,
      STDDEV_SAMP(valuenum) AS stddev_val
    FROM
      vitals_raw
    GROUP BY
      stay_id,
      itemid
    HAVING
      COUNT(valuenum) > 1
  ),
  vitals_normalized AS (
    SELECT
      stay_id,
      (stddev_val - MIN(stddev_val) OVER (PARTITION BY itemid)) / NULLIF(
        MAX(stddev_val) OVER (PARTITION BY itemid) - MIN(stddev_val) OVER (PARTITION BY itemid),
        0
      ) AS normalized_stddev
    FROM
      vitals_stddev
  ),
  instability_scores AS (
    SELECT
      v.stay_id,
      SUM(v.normalized_stddev) * 20 AS instability_score,
      MAX(c.icu_los_days) AS icu_los_days,
      MAX(c.hospital_expire_flag) AS hospital_expire_flag
    FROM
      vitals_normalized v
    INNER JOIN cohort c ON v.stay_id = c.stay_id
    GROUP BY
      v.stay_id
  ),
  ranked_scores AS (
    SELECT
      stay_id,
      instability_score,
      icu_los_days,
      hospital_expire_flag,
      NTILE(10) OVER (ORDER BY instability_score DESC) AS decile
    FROM
      instability_scores
  ),
  percentile_of_65 AS (
    SELECT
      SAFE_DIVIDE(
        (SELECT COUNT(*) FROM ranked_scores WHERE instability_score < 65),
        (SELECT COUNT(*) FROM ranked_scores)
      ) AS percentile_rank_of_65
  ),
  top_decile_metrics AS (
    SELECT
      AVG(icu_los_days) AS avg_los_top_decile,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate_top_decile
    FROM
      ranked_scores
    WHERE
      decile = 1
  )
SELECT
  p.percentile_rank_of_65,
  t.avg_los_top_decile,
  t.mortality_rate_top_decile
FROM
  percentile_of_65 p,
  top_decile_metrics t;
