WITH
  base_cohort AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age AS age_at_icustay,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days
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
      AND (
        DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR)
        + pat.anchor_age
      ) BETWEEN 55 AND 65
  ),
  hfnc_stays AS (
    SELECT DISTINCT
      ce.stay_id
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      base_cohort AS cohort
      ON ce.stay_id = cohort.stay_id
    WHERE
      ce.itemid = 227287
      AND DATETIME_DIFF(ce.charttime, cohort.intime, HOUR) <= 24
  ),
  vitals_first_24h AS (
    SELECT
      ce.stay_id,
      CASE
        WHEN ce.itemid = 220045
        THEN 'HR'
        WHEN ce.itemid IN (220052, 220181)
        THEN 'MAP'
      END AS vital_name,
      ce.valuenum AS value
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      base_cohort AS cohort
      ON ce.stay_id = cohort.stay_id
    WHERE
      ce.itemid IN (
        220045,
        220052,
        220181
      )
      AND ce.valuenum IS NOT NULL AND ce.valuenum > 0
      AND DATETIME_DIFF(ce.charttime, cohort.intime, HOUR) <= 24
  ),
  stay_level_metrics AS (
    SELECT
      stay_id,
      (
        SAFE_DIVIDE(
          STDDEV_SAMP(IF(vital_name = 'HR', value, NULL)),
          AVG(IF(vital_name = 'HR', value, NULL))
        )
      ) + (
        SAFE_DIVIDE(
          STDDEV_SAMP(IF(vital_name = 'MAP', value, NULL)),
          AVG(IF(vital_name = 'MAP', value, NULL))
        )
      ) AS instability_score,
      SAFE_DIVIDE(
        COUNTIF(vital_name = 'HR' AND value > 100),
        COUNTIF(vital_name = 'HR')
      ) AS tachycardia_burden,
      SAFE_DIVIDE(
        COUNTIF(vital_name = 'MAP' AND value < 65),
        COUNTIF(vital_name = 'MAP')
      ) AS hypotension_burden
    FROM
      vitals_first_24h
    GROUP BY
      stay_id
    HAVING
      COUNTIF(vital_name = 'HR') > 2 AND COUNTIF(vital_name = 'MAP') > 2
  ),
  final_cohort_data AS (
    SELECT
      bc.stay_id,
      bc.icu_los_days,
      bc.hospital_expire_flag,
      CASE
        WHEN hs.stay_id IS NOT NULL
        THEN 'HFNC_Target'
        ELSE 'Control'
      END AS cohort_group,
      slm.instability_score,
      slm.tachycardia_burden,
      slm.hypotension_burden
    FROM
      base_cohort AS bc
    LEFT JOIN
      hfnc_stays AS hs
      ON bc.stay_id = hs.stay_id
    INNER JOIN
      stay_level_metrics AS slm
      ON bc.stay_id = slm.stay_id
  )
SELECT
  cohort_group,
  COUNT(DISTINCT stay_id) AS number_of_stays,
  AVG(instability_score) AS avg_instability_score,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(25)] AS instability_score_p25,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(50)] AS instability_score_median,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(75)] AS instability_score_p75,
  APPROX_QUANTILES(instability_score, 100) [OFFSET(95)] AS instability_score_p95,
  AVG(tachycardia_burden) AS avg_tachycardia_burden_proportion,
  AVG(hypotension_burden) AS avg_hypotension_burden_proportion,
  AVG(icu_los_days) AS avg_icu_los_days,
  AVG(CAST(hospital_expire_flag AS INT64)) AS mortality_rate
FROM
  final_cohort_data
GROUP BY
  cohort_group
ORDER BY
  cohort_group DESC;
