WITH
  pneumonia_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      seq_num = 1
      AND (
        (
          icd_version = 9
          AND (
            icd_code = '486'
            OR icd_code LIKE '482%'
            OR icd_code = '485'
          )
        )
        OR
        (
          icd_version = 10
          AND (
            STARTS_WITH(icd_code, 'J18')
            OR STARTS_WITH(icd_code, 'J13')
            OR STARTS_WITH(icd_code, 'J14')
            OR STARTS_WITH(icd_code, 'J15')
          )
        )
      )
  ),
  target_cohort_base AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      (
        EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year
      ) + pat.anchor_age AS admission_age
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON pat.subject_id = adm.subject_id
      INNER JOIN pneumonia_diagnoses AS pdx ON adm.hadm_id = pdx.hadm_id
    WHERE
      pat.gender = 'M'
      AND (
        (
          EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year
        ) + pat.anchor_age
      ) BETWEEN 60 AND 70
  ),
  critical_lab_events AS (
    SELECT
      le.hadm_id,
      le.charttime,
      CASE
        WHEN le.itemid = 50983 AND (le.valuenum < 125 OR le.valuenum > 155) THEN 1
        WHEN le.itemid = 50971 AND (le.valuenum < 3.0 OR le.valuenum > 6.0) THEN 1
        WHEN le.itemid = 50912 AND le.valuenum > 4.0 THEN 1
        WHEN le.itemid = 51301 AND (le.valuenum < 2.0 OR le.valuenum > 20.0) THEN 1
        WHEN le.itemid = 50813 AND le.valuenum > 4.0 THEN 1
        WHEN le.itemid = 50882 AND (le.valuenum < 15 OR le.valuenum > 40) THEN 1
        WHEN le.itemid = 51265 AND le.valuenum < 50 THEN 1
        ELSE 0
      END AS is_critical
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    WHERE
      le.hadm_id IS NOT NULL
      AND le.valuenum IS NOT NULL
      AND le.itemid IN (
        50983, 50971, 50912, 51301, 50813, 50882, 51265
      )
  ),
  cohort_instability_scores AS (
    SELECT
      tcb.hadm_id,
      COUNT(*) AS instability_score
    FROM
      target_cohort_base AS tcb
      INNER JOIN critical_lab_events AS cle ON tcb.hadm_id = cle.hadm_id
    WHERE
      cle.is_critical = 1
      AND cle.charttime BETWEEN tcb.admittime AND DATETIME_ADD(tcb.admittime, INTERVAL 72 HOUR)
    GROUP BY
      tcb.hadm_id
  ),
  cohort_final_data AS (
    SELECT
      tcb.hadm_id,
      tcb.hospital_expire_flag,
      DATETIME_DIFF(tcb.dischtime, tcb.admittime, DAY) AS los_days,
      COALESCE(cis.instability_score, 0) AS instability_score
    FROM
      target_cohort_base AS tcb
      LEFT JOIN cohort_instability_scores AS cis ON tcb.hadm_id = cis.hadm_id
  ),
  all_admissions_instability_scores AS (
    SELECT
      adm.hadm_id,
      COUNT(*) AS instability_score
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN critical_lab_events AS cle ON adm.hadm_id = cle.hadm_id
    WHERE
      cle.is_critical = 1
      AND cle.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 72 HOUR)
    GROUP BY
      adm.hadm_id
  ),
  general_pop_final_data AS (
    SELECT
      adm.hadm_id,
      COALESCE(ais.instability_score, 0) AS instability_score
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      LEFT JOIN all_admissions_instability_scores AS ais ON adm.hadm_id = ais.hadm_id
  ),
  cohort_metrics AS (
    SELECT
      APPROX_QUANTILES(instability_score, 100) [OFFSET(75)] AS p75_instability_score_cohort,
      AVG(instability_score) AS avg_critical_events_cohort,
      AVG(los_days) AS avg_los_days_cohort,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate_cohort,
      COUNT(hadm_id) AS cohort_patient_count
    FROM
      cohort_final_data
  ),
  general_pop_metrics AS (
    SELECT
      AVG(instability_score) AS avg_critical_events_general_pop,
      COUNT(hadm_id) AS general_pop_patient_count
    FROM
      general_pop_final_data
  )
SELECT
  cm.p75_instability_score_cohort,
  cm.avg_critical_events_cohort,
  gpm.avg_critical_events_general_pop,
  cm.avg_los_days_cohort,
  cm.mortality_rate_cohort,
  cm.cohort_patient_count,
  gpm.general_pop_patient_count
FROM
  cohort_metrics AS cm,
  general_pop_metrics AS gpm;
