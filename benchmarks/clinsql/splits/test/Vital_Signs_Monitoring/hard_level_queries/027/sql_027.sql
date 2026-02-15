WITH
  item_ids AS (
    SELECT
      [220052, 220181, 225312] AS map_ids,
      [220045] AS hr_ids,
      [
        225805,
        225807,
        224149,
        224150,
        224151,
        224152,
        224153,
        225441
      ] AS rrt_ids
  ),
  target_demographic_cohort AS (
    SELECT
      icu.stay_id
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    WHERE
      pat.gender = 'F'
      AND ((EXTRACT(YEAR FROM icu.intime) - pat.anchor_year) + pat.anchor_age) BETWEEN 58 AND 68
  ),
  rrt_stays AS (
    SELECT DISTINCT
      stay_id
    FROM `physionet-data.mimiciv_3_1_icu.chartevents`
    WHERE
      itemid IN UNNEST((SELECT rrt_ids FROM item_ids))
  ),
  cohort_groups AS (
    SELECT
      stay_id,
      'Target (Female, 58-68, with RRT)' AS cohort_group
    FROM rrt_stays
    WHERE
      stay_id IN (SELECT stay_id FROM target_demographic_cohort)
    UNION ALL
    SELECT
      stay_id,
      'Control (All other RRT patients)' AS cohort_group
    FROM rrt_stays
    WHERE
      stay_id NOT IN (SELECT stay_id FROM target_demographic_cohort)
  ),
  vitals_hourly AS (
    SELECT
      ce.stay_id,
      DATETIME_TRUNC(ce.charttime, HOUR) AS chart_hour,
      AVG(
        CASE
          WHEN ce.itemid IN UNNEST((SELECT map_ids FROM item_ids)) THEN ce.valuenum
        END
      ) AS avg_map,
      AVG(
        CASE
          WHEN ce.itemid IN UNNEST((SELECT hr_ids FROM item_ids)) THEN ce.valuenum
        END
      ) AS avg_hr
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON ce.stay_id = icu.stay_id
    WHERE
      ce.stay_id IN (SELECT stay_id FROM rrt_stays)
      AND (
        ce.itemid IN UNNEST((SELECT map_ids FROM item_ids))
        OR ce.itemid IN UNNEST((SELECT hr_ids FROM item_ids))
      )
      AND DATETIME_DIFF(ce.charttime, icu.intime, HOUR) BETWEEN 0 AND 71
      AND ce.valuenum IS NOT NULL AND ce.valuenum > 0
    GROUP BY
      ce.stay_id,
      chart_hour
  ),
  patient_level_summary AS (
    SELECT
      v.stay_id,
      cg.cohort_group,
      AVG(
        (CASE WHEN v.avg_map < 65 THEN 1 ELSE 0 END)
        + (CASE WHEN v.avg_hr > 100 THEN 1 ELSE 0 END)
      ) AS vital_instability_index,
      SUM(CASE WHEN v.avg_map < 65 THEN 1 ELSE 0 END) AS hypotensive_hours,
      SUM(CASE WHEN v.avg_hr > 100 THEN 1 ELSE 0 END) AS tachycardic_hours
    FROM vitals_hourly AS v
    INNER JOIN cohort_groups AS cg
      ON v.stay_id = cg.stay_id
    GROUP BY
      v.stay_id,
      cg.cohort_group
  ),
  outcomes AS (
    SELECT
      icu.stay_id,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, DAY) AS icu_los_days
    FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    WHERE
      icu.stay_id IN (SELECT stay_id FROM rrt_stays)
  )
SELECT
  pls.cohort_group,
  COUNT(DISTINCT pls.stay_id) AS num_patients,
  APPROX_QUANTILES(pls.vital_instability_index, 100)[OFFSET(25)] AS p25_instability_index,
  APPROX_QUANTILES(pls.vital_instability_index, 100)[OFFSET(50)] AS p50_instability_index,
  APPROX_QUANTILES(pls.vital_instability_index, 100)[OFFSET(75)] AS p75_instability_index,
  APPROX_QUANTILES(pls.vital_instability_index, 100)[OFFSET(90)] AS p90_instability_index,
  (
    APPROX_QUANTILES(pls.vital_instability_index, 100)[OFFSET(75)]
    - APPROX_QUANTILES(pls.vital_instability_index, 100)[OFFSET(25)]
  ) AS iqr_instability_index,
  AVG(pls.hypotensive_hours) AS avg_hours_with_hypotension,
  AVG(pls.tachycardic_hours) AS avg_hours_with_tachycardia,
  AVG(out.icu_los_days) AS avg_icu_los_days,
  AVG(CAST(out.hospital_expire_flag AS FLOAT64)) AS hospital_mortality_rate
FROM patient_level_summary AS pls
INNER JOIN outcomes AS out
  ON pls.stay_id = out.stay_id
GROUP BY
  pls.cohort_group
ORDER BY
  cohort_group DESC;
