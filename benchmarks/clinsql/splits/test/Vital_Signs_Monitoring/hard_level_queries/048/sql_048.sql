WITH
  demographic_cohort AS (
    SELECT
      p.subject_id,
      i.hadm_id,
      i.stay_id,
      i.intime,
      i.outtime,
      DATETIME_DIFF(i.outtime, i.intime, DAY) AS icu_los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS i
      ON p.subject_id = i.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 75 AND 85
  ),
  ventilation_stays AS (
    SELECT DISTINCT
      stay_id
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
      stay_id IN (SELECT stay_id FROM demographic_cohort)
      AND itemid = 223849
      AND valuenum IS NOT NULL
  ),
  target_cohort AS (
    SELECT
      dc.subject_id,
      dc.hadm_id,
      dc.stay_id,
      dc.intime,
      dc.outtime,
      dc.icu_los_days
    FROM
      demographic_cohort AS dc
    INNER JOIN
      ventilation_stays AS vs
      ON dc.stay_id = vs.stay_id
  ),
  vitals_first_48h AS (
    SELECT
      ce.stay_id,
      ce.charttime,
      MAX(CASE WHEN ce.itemid = 220045 THEN ce.valuenum END) AS heart_rate,
      MAX(CASE WHEN ce.itemid IN (220181, 220052) THEN ce.valuenum END) AS map
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      target_cohort AS tc
      ON ce.stay_id = tc.stay_id
    WHERE
      ce.itemid IN (220045, 220181, 220052)
      AND DATETIME_DIFF(ce.charttime, tc.intime, HOUR) BETWEEN 0 AND 48
    GROUP BY
      ce.stay_id,
      ce.charttime
  ),
  instability_calculations AS (
    SELECT
      stay_id,
      charttime,
      CASE WHEN map < 65 THEN 1 ELSE 0 END AS is_hypotensive,
      CASE WHEN heart_rate > 100 THEN 1 ELSE 0 END AS is_tachycardic,
      (CASE WHEN map < 65 THEN 1 ELSE 0 END) + (CASE WHEN heart_rate > 100 THEN 1 ELSE 0 END) AS point_instability_score
    FROM
      vitals_first_48h
    WHERE
      heart_rate IS NOT NULL
      AND map IS NOT NULL
      AND heart_rate > 0 AND heart_rate < 300
      AND map > 0 AND map < 200
  ),
  stay_level_scores AS (
    SELECT
      ic.stay_id,
      tc.hadm_id,
      tc.icu_los_days,
      AVG(ic.point_instability_score) AS composite_instability_score,
      SUM(ic.is_hypotensive) AS hypotension_episodes_48hr,
      SUM(ic.is_tachycardic) AS tachycardia_episodes_48hr
    FROM
      instability_calculations AS ic
    INNER JOIN
      target_cohort AS tc
      ON ic.stay_id = tc.stay_id
    GROUP BY
      ic.stay_id,
      tc.hadm_id,
      tc.icu_los_days
  ),
  ranked_stays AS (
    SELECT
      sls.stay_id,
      sls.composite_instability_score,
      sls.hypotension_episodes_48hr,
      sls.tachycardia_episodes_48hr,
      sls.icu_los_days,
      adm.hospital_expire_flag AS mortality_flag,
      NTILE(4) OVER (
        ORDER BY
          sls.composite_instability_score DESC
      ) AS instability_quartile
    FROM
      stay_level_scores AS sls
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON sls.hadm_id = adm.hadm_id
  ),
  percentile_90_value AS (
    SELECT
      APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(90)] AS p90_instability_score
    FROM
      stay_level_scores
  )
SELECT
  CASE
    WHEN rs.instability_quartile = 1
    THEN 'Top 25% Most Unstable'
    ELSE 'Bottom 75% Less Unstable'
  END AS Risk_Group,
  p90.p90_instability_score AS P90_Instability_Score_Overall_Cohort,
  COUNT(DISTINCT rs.stay_id) AS Patient_Count,
  AVG(rs.composite_instability_score) AS Avg_Composite_Instability_Score,
  AVG(rs.hypotension_episodes_48hr) AS Avg_Hypotension_Episodes_48hr,
  AVG(rs.tachycardia_episodes_48hr) AS Avg_Tachycardia_Episodes_48hr,
  AVG(rs.icu_los_days) AS Avg_ICU_LOS_Days,
  AVG(rs.mortality_flag) AS Mortality_Rate
FROM
  ranked_stays AS rs,
  percentile_90_value AS p90
GROUP BY
  Risk_Group,
  p90.p90_instability_score
ORDER BY
  Risk_Group DESC;
