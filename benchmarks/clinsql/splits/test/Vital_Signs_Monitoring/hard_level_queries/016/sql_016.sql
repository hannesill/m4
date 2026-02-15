WITH
  icustay_details AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      ON icu.subject_id = pat.subject_id
    WHERE
      pat.gender = 'M'
      AND (
        DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age
      ) BETWEEN 57 AND 67
  ),
  transplant_cohort_ids AS (
    SELECT DISTINCT
      dx.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    WHERE
      dx.hadm_id IN (SELECT hadm_id FROM icustay_details)
      AND (
        (dx.icd_version = 9 AND (STARTS_WITH(dx.icd_code, 'V42') OR STARTS_WITH(dx.icd_code, '9968')))
        OR (dx.icd_version = 10 AND (STARTS_WITH(dx.icd_code, 'Z94') OR STARTS_WITH(dx.icd_code, 'T86')))
      )
  ),
  cohorts AS (
    SELECT
      id.stay_id,
      id.hadm_id,
      id.intime,
      id.icu_los_hours,
      CASE
        WHEN id.hadm_id IN (SELECT hadm_id FROM transplant_cohort_ids)
          THEN 'Transplant'
        ELSE 'Non-Transplant'
      END AS cohort_group
    FROM
      icustay_details AS id
  ),
  filtered_vitals AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.charttime,
      ce.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    WHERE
      ce.stay_id IN (SELECT stay_id FROM cohorts)
      AND ce.itemid IN (
        220277,
        220210,
        224690,
        223762,
        223761
      )
      AND ce.charttime BETWEEN (SELECT MIN(intime) FROM cohorts) AND (SELECT MAX(DATETIME_ADD(intime, INTERVAL 72 HOUR)) FROM cohorts)
  ),
  abnormal_events AS (
    SELECT
      fv.stay_id,
      CASE
        WHEN fv.itemid = 223762 AND fv.valuenum > 38.5 THEN 1
        WHEN fv.itemid = 223761 AND ( (fv.valuenum - 32) * 5 / 9 ) > 38.5 THEN 1
        ELSE 0
      END AS is_fever,
      CASE
        WHEN fv.itemid = 220277 AND fv.valuenum < 90 THEN 1
        ELSE 0
      END AS is_hypoxemia,
      CASE
        WHEN fv.itemid IN (220210, 224690) AND fv.valuenum > 20 THEN 1
        ELSE 0
      END AS is_tachypnea
    FROM
      filtered_vitals AS fv
    INNER JOIN
      cohorts AS co
      ON fv.stay_id = co.stay_id
    WHERE
      DATETIME_DIFF(fv.charttime, co.intime, HOUR) <= 72
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(is_fever) + SUM(is_hypoxemia) + SUM(is_tachypnea) AS composite_instability_score
    FROM
      abnormal_events
    GROUP BY
      stay_id
  ),
  final_cohort_data AS (
    SELECT
      co.stay_id,
      co.cohort_group,
      co.icu_los_hours,
      adm.hospital_expire_flag,
      COALESCE(iss.composite_instability_score, 0) AS composite_instability_score
    FROM
      cohorts AS co
    LEFT JOIN
      instability_scores AS iss
      ON co.stay_id = iss.stay_id
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON co.hadm_id = adm.hadm_id
  )
SELECT
  cohort_group,
  COUNT(DISTINCT stay_id) AS patient_count,
  ROUND(AVG(icu_los_hours / 24), 2) AS avg_icu_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(composite_instability_score), 2) AS avg_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(25)] AS p25_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(50)] AS median_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(75)] AS p75_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(90)] AS p90_instability_score,
  APPROX_QUANTILES(composite_instability_score, 100)[OFFSET(95)] AS p95_instability_score
FROM
  final_cohort_data
GROUP BY
  cohort_group
ORDER BY
  cohort_group DESC;
