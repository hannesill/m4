WITH
  cohort_admissions AS (
    SELECT
      adm.hadm_id,
      adm.subject_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      (
        EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year + pat.anchor_age
      ) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON adm.hadm_id = dx.hadm_id
    WHERE
      pat.gender = 'M'
      AND (
        (dx.icd_version = 9 AND dx.icd_code = '5770')
        OR (dx.icd_version = 10 AND STARTS_WITH(dx.icd_code, 'K85'))
      )
      AND (
        EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year + pat.anchor_age
      ) BETWEEN 63 AND 73
    GROUP BY
      adm.hadm_id,
      adm.subject_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      age_at_admission
  ),
  critical_lab_definitions AS (
    SELECT 50912 AS itemid, 'Creatinine' AS lab_name, NULL AS critical_low, 4.0 AS critical_high UNION ALL
    SELECT 51003, 'Troponin T', NULL, 0.04 UNION ALL
    SELECT 50983, 'Sodium', 120, 160 UNION ALL
    SELECT 50971, 'Potassium', 2.5, 6.5 UNION ALL
    SELECT 50931, 'Glucose', 70, 400 UNION ALL
    SELECT 51006, 'BUN', NULL, 100.0
  ),
  all_labevents_first72h AS (
    SELECT
      le.hadm_id,
      cld.lab_name,
      CASE
        WHEN le.valuenum < cld.critical_low OR le.valuenum > cld.critical_high THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON le.hadm_id = adm.hadm_id
      INNER JOIN critical_lab_definitions AS cld ON le.itemid = cld.itemid
    WHERE
      le.valuenum IS NOT NULL
      AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 72 HOUR)
  ),
  cohort_instability_scores AS (
    SELECT
      ca.hadm_id,
      ca.hospital_expire_flag,
      DATETIME_DIFF(ca.dischtime, ca.admittime, DAY) AS length_of_stay,
      COALESCE(SUM(alf.is_critical), 0) AS instability_score
    FROM
      cohort_admissions AS ca
      LEFT JOIN all_labevents_first72h AS alf ON ca.hadm_id = alf.hadm_id
    GROUP BY
      ca.hadm_id,
      ca.hospital_expire_flag,
      length_of_stay
  ),
  cohort_score_percentile AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(90)] AS p90_instability_score,
      COUNT(hadm_id) AS cohort_total_patients
    FROM
      cohort_instability_scores
  ),
  top_tier_summary_outcomes AS (
    SELECT
      COUNT(cis.hadm_id) AS top_tier_patient_count,
      AVG(cis.hospital_expire_flag) AS mortality_rate_top_tier,
      AVG(cis.length_of_stay) AS avg_los_top_tier
    FROM
      cohort_instability_scores AS cis
      CROSS JOIN cohort_score_percentile AS csp
    WHERE
      cis.instability_score >= csp.p90_instability_score
  ),
  top_tier_hadms AS (
    SELECT
      cis.hadm_id
    FROM
      cohort_instability_scores AS cis
    WHERE
      cis.instability_score >= (SELECT p90_instability_score FROM cohort_score_percentile)
  ),
  critical_lab_rates AS (
    SELECT
      alf.lab_name,
      SAFE_DIVIDE(
        COUNTIF(tth.hadm_id IS NOT NULL AND alf.is_critical = 1),
        COUNTIF(tth.hadm_id IS NOT NULL)
      ) AS critical_rate_top_tier_cohort,
      SAFE_DIVIDE(
        SUM(alf.is_critical),
        COUNT(alf.hadm_id)
      ) AS critical_rate_general_pop
    FROM
      all_labevents_first72h AS alf
      LEFT JOIN top_tier_hadms AS tth ON alf.hadm_id = tth.hadm_id
    GROUP BY
      alf.lab_name
  )
SELECT
  csp.cohort_total_patients,
  csp.p90_instability_score,
  outcomes.top_tier_patient_count,
  outcomes.mortality_rate_top_tier,
  outcomes.avg_los_top_tier,
  rates.lab_name,
  rates.critical_rate_top_tier_cohort,
  rates.critical_rate_general_pop
FROM
  critical_lab_rates AS rates
  CROSS JOIN cohort_score_percentile AS csp
  CROSS JOIN top_tier_summary_outcomes AS outcomes
ORDER BY
  rates.lab_name;
