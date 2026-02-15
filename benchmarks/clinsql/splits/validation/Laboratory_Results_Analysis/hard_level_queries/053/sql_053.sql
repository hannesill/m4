WITH
  cohort_admissions AS (
    SELECT DISTINCT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      (
        EXTRACT(
          YEAR
          FROM adm.admittime
        ) - pat.anchor_year
      ) + pat.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON adm.hadm_id = dx.hadm_id
    WHERE
      pat.gender = 'M'
      AND (
        dx.icd_code LIKE '578%'
        OR dx.icd_code LIKE '569.3%'
        OR dx.icd_code LIKE 'K92.1%'
        OR dx.icd_code LIKE 'K92.2%'
        OR dx.icd_code LIKE 'K62.5%'
      )
      AND (
        (
          EXTRACT(
            YEAR
            FROM adm.admittime
          ) - pat.anchor_year
        ) + pat.anchor_age
      ) BETWEEN 68 AND 78
  ),
  critical_labs_first_72h AS (
    SELECT
      le.hadm_id,
      le.itemid,
      CASE
        WHEN le.itemid IN (50824, 50983) AND (le.valuenum < 120 OR le.valuenum > 160) THEN 1
        WHEN le.itemid IN (50822, 50971) AND (le.valuenum < 2.5 OR le.valuenum > 6.5) THEN 1
        WHEN le.itemid = 50912 AND le.valuenum > 4.0 THEN 1
        WHEN le.itemid = 51222 AND le.valuenum < 7.0 THEN 1
        WHEN le.itemid = 51265 AND le.valuenum < 20 THEN 1
        WHEN le.itemid IN (51301, 51300) AND (le.valuenum < 1.0 OR le.valuenum > 50.0) THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
    WHERE
      TIMESTAMP_DIFF(le.charttime, adm.admittime, HOUR) BETWEEN 0 AND 72
      AND le.valuenum IS NOT NULL
      AND le.itemid IN (
        50824, 50983,
        50822, 50971,
        50912,
        51222,
        51265,
        51301, 51300
      )
  ),
  instability_scores AS (
    SELECT
      hadm_id,
      SUM(is_critical) AS instability_score
    FROM
      critical_labs_first_72h
    GROUP BY
      hadm_id
  ),
  cohort_instability AS (
    SELECT
      ca.hadm_id,
      ca.hospital_expire_flag,
      ca.admittime,
      ca.dischtime,
      COALESCE(iss.instability_score, 0) AS instability_score
    FROM
      cohort_admissions AS ca
      LEFT JOIN instability_scores AS iss ON ca.hadm_id = iss.hadm_id
  ),
  cohort_percentile AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(90)] AS p90_instability_score
    FROM
      cohort_instability
  ),
  top_tier_cohort AS (
    SELECT
      ci.*
    FROM
      cohort_instability AS ci
      CROSS JOIN cohort_percentile AS cp
    WHERE
      ci.instability_score > cp.p90_instability_score
  ),
  top_tier_summary AS (
    SELECT
      COUNT(hadm_id) AS top_tier_patient_count,
      AVG(hospital_expire_flag) AS top_tier_mortality_rate,
      AVG(
        TIMESTAMP_DIFF(dischtime, admittime, HOUR) / 24.0
      ) AS top_tier_avg_los_days
    FROM
      top_tier_cohort
  ),
  top_tier_critical_breakdown AS (
    SELECT
      cl.itemid,
      SUM(cl.is_critical) AS critical_event_count,
      COUNT(DISTINCT cl.hadm_id) AS patients_with_critical_event
    FROM
      critical_labs_first_72h AS cl
      INNER JOIN top_tier_cohort AS ttc ON cl.hadm_id = ttc.hadm_id
    WHERE
      cl.is_critical = 1
    GROUP BY
      cl.itemid
  ),
  general_pop_critical_breakdown AS (
    SELECT
      itemid,
      SUM(is_critical) AS critical_event_count,
      COUNT(DISTINCT hadm_id) AS patients_with_critical_event
    FROM
      critical_labs_first_72h
    WHERE
      is_critical = 1
    GROUP BY
      itemid
  ),
  population_counts AS (
    SELECT
      (
        SELECT
          COUNT(DISTINCT hadm_id)
        FROM
          cohort_admissions
      ) AS cohort_total_patients,
      (
        SELECT
          COUNT(DISTINCT hadm_id)
        FROM
          `physionet-data.mimiciv_3_1_hosp.admissions`
      ) AS general_total_patients
  )
SELECT
  cp.p90_instability_score,
  tts.top_tier_patient_count,
  ROUND(tts.top_tier_mortality_rate, 3) AS top_tier_mortality_rate,
  ROUND(tts.top_tier_avg_los_days, 1) AS top_tier_avg_los_days,
  dli.label AS critical_lab_test,
  tt.critical_event_count AS top_tier_critical_event_count,
  ROUND(
    tt.patients_with_critical_event / tts.top_tier_patient_count,
    3
  ) AS top_tier_proportion_of_patients_affected,
  gp.critical_event_count AS general_pop_critical_event_count,
  ROUND(
    gp.patients_with_critical_event / pc.general_total_patients,
    3
  ) AS general_pop_proportion_of_patients_affected,
  ROUND(
    (
      tt.patients_with_critical_event / tts.top_tier_patient_count
    ) / (
      gp.patients_with_critical_event / pc.general_total_patients
    ),
    1
  ) AS relative_risk_vs_general_pop
FROM
  top_tier_critical_breakdown AS tt
  LEFT JOIN general_pop_critical_breakdown AS gp ON tt.itemid = gp.itemid
  LEFT JOIN `physionet-data.mimiciv_3_1_hosp.d_labitems` AS dli ON tt.itemid = dli.itemid
  CROSS JOIN cohort_percentile AS cp
  CROSS JOIN top_tier_summary AS tts
  CROSS JOIN population_counts AS pc
ORDER BY
  relative_risk_vs_general_pop DESC,
  top_tier_critical_event_count DESC;
