WITH
  asthma_cohort_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age) BETWEEN 39 AND 49
      AND a.hadm_id IN (
        SELECT DISTINCT hadm_id
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          (icd_version = 9 AND (icd_code LIKE '493__1' OR icd_code LIKE '493__2'))
          OR (icd_version = 10 AND icd_code LIKE 'J45_%1')
      )
  ),
  critical_lab_definitions AS (
    SELECT * FROM UNNEST([
      STRUCT('Potassium' AS lab_name, 50971 AS itemid, 2.5 AS crit_low, 6.0 AS crit_high),
      STRUCT('Sodium' AS lab_name, 50983 AS itemid, 120.0 AS crit_low, 160.0 AS crit_high),
      STRUCT('Creatinine' AS lab_name, 50912 AS itemid, NULL AS crit_low, 4.0 AS crit_high),
      STRUCT('WBC' AS lab_name, 51301 AS itemid, 2.0 AS crit_low, 30.0 AS crit_high),
      STRUCT('Platelet' AS lab_name, 51265 AS itemid, 20.0 AS crit_low, NULL AS crit_high),
      STRUCT('Lactate' AS lab_name, 50813 AS itemid, NULL AS crit_low, 4.0 AS crit_high),
      STRUCT('Anion Gap' AS lab_name, 50868 AS itemid, NULL AS crit_low, 20.0 AS crit_high)
    ])
  ),
  all_critical_events AS (
    SELECT
      le.subject_id,
      le.hadm_id,
      le.charttime
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      critical_lab_definitions AS cld
      ON le.itemid = cld.itemid
    WHERE
      le.valuenum IS NOT NULL
      AND (le.valuenum < cld.crit_low OR le.valuenum > cld.crit_high)
  ),
  cohort_critical_events_48h AS (
    SELECT
      ace.hadm_id
    FROM
      all_critical_events AS ace
    INNER JOIN
      asthma_cohort_admissions AS aca
      ON ace.hadm_id = aca.hadm_id
    WHERE
      ace.charttime >= aca.admittime
      AND ace.charttime <= DATETIME_ADD(aca.admittime, INTERVAL 48 HOUR)
  ),
  cohort_instability_scores AS (
    SELECT
      hadm_id,
      COUNT(*) AS instability_score
    FROM
      cohort_critical_events_48h
    GROUP BY
      hadm_id
  ),
  general_inpatient_critical_events_48h AS (
    SELECT
      ace.hadm_id
    FROM
      all_critical_events AS ace
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON ace.hadm_id = a.hadm_id
    WHERE
      ace.charttime >= a.admittime
      AND ace.charttime <= DATETIME_ADD(a.admittime, INTERVAL 48 HOUR)
  )
SELECT
  'Female, 39-49, Asthma Exacerbation' AS cohort_description,
  (SELECT COUNT(DISTINCT subject_id) FROM asthma_cohort_admissions) AS cohort_patient_count,
  (SELECT COUNT(DISTINCT hadm_id) FROM asthma_cohort_admissions) AS cohort_admission_count,
  (
    SELECT
      APPROX_QUANTILES(instability_score, 100)[OFFSET(75)]
    FROM
      cohort_instability_scores
  ) AS p75_instability_score_first_48h,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM cohort_critical_events_48h),
    (SELECT COUNT(DISTINCT hadm_id) FROM asthma_cohort_admissions)
  ) AS cohort_avg_critical_events_per_admission,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM general_inpatient_critical_events_48h),
    (SELECT COUNT(DISTINCT hadm_id) FROM `physionet-data.mimiciv_3_1_hosp.admissions`)
  ) AS general_avg_critical_events_per_admission,
  (
    SELECT
      AVG(DATETIME_DIFF(dischtime, admittime, DAY))
    FROM
      asthma_cohort_admissions
  ) AS cohort_avg_los_days,
  (
    SELECT
      AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100
    FROM
      asthma_cohort_admissions
  ) AS cohort_mortality_rate_percent;
