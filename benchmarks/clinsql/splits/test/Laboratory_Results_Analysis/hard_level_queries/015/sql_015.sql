WITH
  stroke_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND (
          icd_code LIKE '433_1'
          OR icd_code LIKE '434_1'
        )
      )
      OR (
        icd_version = 10
        AND icd_code LIKE 'I63%'
      )
  ),
  cohort_base AS (
    SELECT
      p.subject_id,
      adm.hadm_id,
      p.gender,
      (EXTRACT(YEAR FROM adm.admittime) - p.anchor_year) + p.anchor_age AS age_at_admission,
      adm.admittime,
      adm.dischtime,
      DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS los_days,
      adm.hospital_expire_flag,
      CASE
        WHEN sa.hadm_id IS NOT NULL THEN 'Stroke'
        ELSE 'Control'
      END AS cohort_type
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON adm.subject_id = p.subject_id
      LEFT JOIN stroke_admissions AS sa ON adm.hadm_id = sa.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        (EXTRACT(YEAR FROM adm.admittime) - p.anchor_year) + p.anchor_age
      ) BETWEEN 49 AND 59
  ),
  lab_abnormalities AS (
    SELECT
      c.hadm_id,
      c.cohort_type,
      CASE WHEN le.itemid = 50983 AND (le.valuenum < 125 OR le.valuenum > 155) THEN 1 ELSE 0 END AS is_crit_sodium,
      CASE WHEN le.itemid = 50971 AND (le.valuenum < 3.0 OR le.valuenum > 6.0) THEN 1 ELSE 0 END AS is_crit_potassium,
      CASE WHEN le.itemid = 50912 AND le.valuenum > 2.0 THEN 1 ELSE 0 END AS is_crit_creatinine,
      CASE WHEN le.itemid = 51003 AND le.valuenum > 0.01 THEN 1 ELSE 0 END AS is_crit_troponin_t,
      CASE WHEN le.itemid = 50931 AND (le.valuenum < 60 OR le.valuenum > 400) THEN 1 ELSE 0 END AS is_crit_glucose,
      CASE WHEN le.itemid = 51006 AND le.valuenum > 40 THEN 1 ELSE 0 END AS is_crit_bun
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN cohort_base AS c ON le.hadm_id = c.hadm_id
    WHERE
      le.charttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 72 HOUR)
      AND le.valuenum IS NOT NULL
      AND le.itemid IN (
        50983,
        50971,
        50912,
        51003,
        50931,
        51006
      )
  ),
  patient_scores AS (
    SELECT
      cb.hadm_id,
      cb.cohort_type,
      cb.los_days,
      cb.hospital_expire_flag,
      SUM(
        la.is_crit_sodium + la.is_crit_potassium + la.is_crit_creatinine
        + la.is_crit_troponin_t + la.is_crit_glucose + la.is_crit_bun
      ) AS instability_score,
      SUM(la.is_crit_sodium) AS count_crit_sodium,
      SUM(la.is_crit_potassium) AS count_crit_potassium,
      SUM(la.is_crit_creatinine) AS count_crit_creatinine,
      SUM(la.is_crit_troponin_t) AS count_crit_troponin_t,
      SUM(la.is_crit_glucose) AS count_crit_glucose,
      SUM(la.is_crit_bun) AS count_crit_bun
    FROM
      cohort_base AS cb
      LEFT JOIN lab_abnormalities AS la ON cb.hadm_id = la.hadm_id
    GROUP BY
      cb.hadm_id,
      cb.cohort_type,
      cb.los_days,
      cb.hospital_expire_flag
  ),
  stroke_cohort_ranked AS (
    SELECT
      ps.*,
      PERCENTILE_CONT(ps.instability_score, 0.75) OVER () AS p75_instability_score,
      CASE
        WHEN ps.instability_score >= PERCENTILE_CONT(ps.instability_score, 0.75) OVER () THEN 'Stroke_High_Instability'
        ELSE 'Stroke_Low_Instability'
      END AS final_group
    FROM
      patient_scores AS ps
    WHERE
      ps.cohort_type = 'Stroke'
  ),
  final_groups AS (
    SELECT
      hadm_id,
      final_group,
      p75_instability_score,
      instability_score,
      los_days,
      hospital_expire_flag,
      count_crit_sodium,
      count_crit_potassium,
      count_crit_creatinine,
      count_crit_troponin_t,
      count_crit_glucose,
      count_crit_bun
    FROM
      stroke_cohort_ranked
    UNION ALL
    SELECT
      hadm_id,
      'Control_Group' AS final_group,
      NULL AS p75_instability_score,
      instability_score,
      los_days,
      hospital_expire_flag,
      count_crit_sodium,
      count_crit_potassium,
      count_crit_creatinine,
      count_crit_troponin_t,
      count_crit_glucose,
      count_crit_bun
    FROM
      patient_scores
    WHERE
      cohort_type = 'Control'
  )
SELECT
  final_group,
  MAX(p75_instability_score) AS p75_score_threshold,
  COUNT(hadm_id) AS number_of_patients,
  AVG(instability_score) AS avg_instability_score,
  AVG(los_days) AS avg_length_of_stay_days,
  AVG(hospital_expire_flag) * 100 AS mortality_rate_percent,
  SUM(count_crit_sodium) / COUNT(hadm_id) AS critical_sodium_rate,
  SUM(count_crit_potassium) / COUNT(hadm_id) AS critical_potassium_rate,
  SUM(count_crit_creatinine) / COUNT(hadm_id) AS critical_creatinine_rate,
  SUM(count_crit_troponin_t) / COUNT(hadm_id) AS critical_troponin_t_rate,
  SUM(count_crit_glucose) / COUNT(hadm_id) AS critical_glucose_rate,
  SUM(count_crit_bun) / COUNT(hadm_id) AS critical_bun_rate
FROM
  final_groups
WHERE
  final_group IN ('Stroke_High_Instability', 'Control_Group')
GROUP BY
  final_group
ORDER BY
  final_group DESC;
