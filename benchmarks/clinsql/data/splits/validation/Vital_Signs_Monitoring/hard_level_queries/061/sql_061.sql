WITH
  acs_cohort AS (
    SELECT
      icu.subject_id,
      icu.hadm_id,
      icu.stay_id,
      icu.intime,
      icu.outtime,
      p.anchor_age,
      (DATETIME_DIFF(icu.intime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) AS age_at_icu_admission
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p ON icu.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (DATETIME_DIFF(icu.intime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) BETWEEN 49 AND 59
      AND icu.hadm_id IN (
        SELECT DISTINCT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
          OR (icd_version = 9 AND icd_code = '4111')
          OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I21')
          OR (icd_version = 10 AND icd_code = 'I200')
      )
  ),
  vitals_first_24h AS (
    SELECT
      ce.stay_id,
      ce.itemid,
      ce.charttime,
      CASE
        WHEN ce.itemid = 223762 THEN (ce.valuenum - 32) * 5 / 9
        ELSE ce.valuenum
      END AS value_standardized
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN
      acs_cohort AS cohort ON ce.stay_id = cohort.stay_id
    WHERE
      ce.charttime BETWEEN cohort.intime AND DATETIME_ADD(cohort.intime, INTERVAL 24 HOUR)
      AND ce.itemid IN (
        220045,
        220179,
        220050,
        225312,
        220052,
        220277,
        220210,
        223761,
        223762
      )
      AND ce.valuenum IS NOT NULL
  ),
  abnormal_flags AS (
    SELECT
      stay_id,
      charttime,
      CASE WHEN itemid = 220045 AND (value_standardized < 50 OR value_standardized > 120) THEN 1 ELSE 0 END AS hr_abnormal,
      CASE WHEN itemid IN (220179, 220050) AND value_standardized < 90 THEN 1 ELSE 0 END AS sbp_abnormal,
      CASE WHEN itemid IN (225312, 220052) AND value_standardized < 65 THEN 1 ELSE 0 END AS map_abnormal,
      CASE WHEN itemid = 220277 AND value_standardized < 90 THEN 1 ELSE 0 END AS spo2_abnormal,
      CASE WHEN itemid = 220210 AND (value_standardized < 10 OR value_standardized > 30) THEN 1 ELSE 0 END AS rr_abnormal,
      CASE WHEN itemid IN (223761, 223762) AND (value_standardized < 36 OR value_standardized > 38.5) THEN 1 ELSE 0 END AS temp_abnormal
    FROM
      vitals_first_24h
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(hr_abnormal + sbp_abnormal + map_abnormal + spo2_abnormal + rr_abnormal + temp_abnormal) AS composite_instability_score
    FROM
      abnormal_flags
    GROUP BY
      stay_id
  ),
  ranked_cohort AS (
    SELECT
      sc.stay_id,
      sc.composite_instability_score,
      NTILE(10) OVER (ORDER BY sc.composite_instability_score DESC) AS instability_decile
    FROM
      instability_scores AS sc
  ),
  top_decile_outcomes AS (
    SELECT
      COUNT(DISTINCT r.stay_id) AS number_of_patients,
      AVG(DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0) AS avg_icu_los_days,
      AVG(adm.hospital_expire_flag) * 100 AS mortality_rate_percent
    FROM
      ranked_cohort AS r
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON r.stay_id = icu.stay_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
    WHERE
      r.instability_decile = 1
  ),
  percentile_calculation AS (
    SELECT
      COUNT(*) AS number_of_patients,
      SAFE_DIVIDE(
        SUM(IF(composite_instability_score < 70, 1, 0)),
        COUNT(*)
      ) * 100 AS calculated_value,
      CAST(NULL AS FLOAT64) AS calculated_value_2
    FROM
      instability_scores
  )
SELECT
  pc.number_of_patients AS cohort_size,
  pc.calculated_value AS result_metric_1,
  pc.calculated_value_2 AS result_metric_2
FROM
  percentile_calculation AS pc
UNION ALL
SELECT
  tdo.number_of_patients,
  tdo.avg_icu_los_days,
  tdo.mortality_rate_percent
FROM
  top_decile_outcomes AS tdo;
