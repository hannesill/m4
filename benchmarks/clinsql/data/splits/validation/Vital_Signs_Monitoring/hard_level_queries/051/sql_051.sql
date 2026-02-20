WITH
  icu_patient_base AS (
    SELECT
      pat.subject_id,
      icu.hadm_id,
      icu.stay_id,
      pat.gender,
      icu.intime,
      icu.outtime,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age AS age_at_icustay,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON icu.hadm_id = adm.hadm_id
    WHERE
      pat.gender = 'M'
      AND (DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age) BETWEEN 89 AND 99
  ),
  stroke_cohort_ids AS (
    SELECT DISTINCT
      icu.stay_id
    FROM
      icu_patient_base AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON icu.hadm_id = dx.hadm_id
    WHERE
      (dx.icd_version = 9 AND (dx.icd_code LIKE '433%' OR dx.icd_code LIKE '434%'))
      OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I63%')
  ),
  cohorts AS (
    SELECT
      base.*,
      CASE
        WHEN base.stay_id IN (SELECT stay_id FROM stroke_cohort_ids)
        THEN 'Ischemic Stroke (89-99 M)'
        ELSE 'General ICU (89-99 M)'
      END AS cohort_group
    FROM
      icu_patient_base AS base
  ),
  vitals_first_48h AS (
    SELECT
      ce.stay_id,
      ce.valuenum,
      CASE
        WHEN ce.itemid = 220045 THEN 'HR'
        WHEN ce.itemid IN (220179, 220050) THEN 'SBP'
        WHEN ce.itemid = 220210 THEN 'RR'
        WHEN ce.itemid = 220277 THEN 'SPO2'
      END AS vital_sign_name
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      cohorts
      ON ce.stay_id = cohorts.stay_id
    WHERE
      ce.itemid IN (
        220045,
        220179,
        220050,
        220210,
        220277
      )
      AND ce.charttime BETWEEN cohorts.intime AND DATETIME_ADD(cohorts.intime, INTERVAL 48 HOUR)
      AND ce.valuenum > 0 AND ce.valuenum < 300
  ),
  vital_cv_per_patient AS (
    SELECT
      stay_id,
      vital_sign_name,
      SAFE_DIVIDE(STDDEV(valuenum), AVG(valuenum)) AS cv
    FROM
      vitals_first_48h
    GROUP BY
      stay_id,
      vital_sign_name
    HAVING
      COUNT(valuenum) > 1
  ),
  instability_score AS (
    SELECT
      stay_id,
      (
        COALESCE(AVG(CASE WHEN vital_sign_name = 'HR' THEN cv END), 0) +
        COALESCE(AVG(CASE WHEN vital_sign_name = 'SBP' THEN cv END), 0) +
        COALESCE(AVG(CASE WHEN vital_sign_name = 'RR' THEN cv END), 0) +
        COALESCE(AVG(CASE WHEN vital_sign_name = 'SPO2' THEN cv END), 0)
      ) / NULLIF(
        (CASE WHEN AVG(CASE WHEN vital_sign_name = 'HR' THEN cv END) IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN AVG(CASE WHEN vital_sign_name = 'SBP' THEN cv END) IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN AVG(CASE WHEN vital_sign_name = 'RR' THEN cv END) IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN AVG(CASE WHEN vital_sign_name = 'SPO2' THEN cv END) IS NOT NULL THEN 1 ELSE 0 END), 0
      ) AS instability_score
    FROM
      vital_cv_per_patient
    GROUP BY
      stay_id
  ),
  abnormal_episodes AS (
    SELECT
      stay_id,
      COUNTIF(
        (vital_sign_name = 'HR' AND (valuenum < 60 OR valuenum > 100)) OR
        (vital_sign_name = 'SBP' AND (valuenum < 90 OR valuenum > 160)) OR
        (vital_sign_name = 'RR' AND (valuenum < 12 OR valuenum > 25)) OR
        (vital_sign_name = 'SPO2' AND valuenum < 92)
      ) AS total_abnormal_episodes
    FROM
      vitals_first_48h
    GROUP BY
      stay_id
  ),
  final_patient_data AS (
    SELECT
      co.stay_id,
      co.cohort_group,
      co.icu_los_hours,
      co.hospital_expire_flag,
      inst.instability_score,
      abn.total_abnormal_episodes,
      NTILE(4) OVER (ORDER BY inst.instability_score DESC) AS instability_quartile
    FROM
      cohorts AS co
    LEFT JOIN
      instability_score AS inst
      ON co.stay_id = inst.stay_id
    LEFT JOIN
      abnormal_episodes AS abn
      ON co.stay_id = abn.stay_id
    WHERE
      inst.instability_score IS NOT NULL
  ),
  stroke_percentile AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(95)] AS p95_instability_score_stroke_group
    FROM
      final_patient_data
    WHERE
      cohort_group = 'Ischemic Stroke (89-99 M)'
  )
SELECT
  fpd.cohort_group,
  sp.p95_instability_score_stroke_group,
  COUNT(DISTINCT fpd.stay_id) AS num_patients_in_top_quartile,
  AVG(fpd.instability_score) AS avg_instability_score_in_top_quartile,
  AVG(fpd.total_abnormal_episodes) AS avg_abnormal_episodes_in_top_quartile,
  AVG(fpd.icu_los_hours) AS avg_icu_los_hours_in_top_quartile,
  AVG(CAST(fpd.hospital_expire_flag AS FLOAT64)) AS mortality_rate_in_top_quartile
FROM
  final_patient_data AS fpd,
  stroke_percentile AS sp
WHERE
  fpd.instability_quartile = 1
GROUP BY
  fpd.cohort_group,
  sp.p95_instability_score_stroke_group
ORDER BY
  fpd.cohort_group;
