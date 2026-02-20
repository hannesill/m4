WITH
cohort_admissions AS (
  SELECT DISTINCT
    adm.hadm_id,
    adm.subject_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON adm.hadm_id = dx.hadm_id
  WHERE
    pat.gender = 'M'
    AND (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age BETWEEN 40 AND 50
    AND (
      dx.icd_code LIKE '430%' OR dx.icd_code LIKE '431%' OR dx.icd_code LIKE '432%'
      OR dx.icd_code LIKE 'I60%' OR dx.icd_code LIKE 'I61%' OR dx.icd_code LIKE 'I62%'
    )
),
lab_panel AS (
  SELECT 50912 AS itemid, 'Creatinine' AS lab_name, 1.5 AS upper_bound, NULL AS lower_bound UNION ALL
  SELECT 51006, 'BUN', 25, NULL UNION ALL
  SELECT 50983, 'Sodium', 145, 135 UNION ALL
  SELECT 50971, 'Potassium', 5.2, 3.5 UNION ALL
  SELECT 51301, 'WBC', 12, 4 UNION ALL
  SELECT 51265, 'Platelets', NULL, 150 UNION ALL
  SELECT 51222, 'Hemoglobin', NULL, 10 UNION ALL
  SELECT 50813, 'Lactate', 2, NULL UNION ALL
  SELECT 50882, 'Bicarbonate', 29, 22
),
labs_first_72h AS (
  SELECT
    le.hadm_id,
    le.itemid,
    lp.lab_name,
    CASE
      WHEN lp.lower_bound IS NULL AND le.valuenum > lp.upper_bound THEN 1
      WHEN lp.upper_bound IS NULL AND le.valuenum < lp.lower_bound THEN 1
      WHEN le.valuenum < lp.lower_bound OR le.valuenum > lp.upper_bound THEN 1
      ELSE 0
    END AS is_abnormal,
    CASE
      WHEN ca.hadm_id IS NOT NULL THEN 1
      ELSE 0
    END AS is_target_cohort
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    ON le.hadm_id = adm.hadm_id
  INNER JOIN
    lab_panel AS lp
    ON le.itemid = lp.itemid
  LEFT JOIN
    cohort_admissions AS ca
    ON le.hadm_id = ca.hadm_id
  WHERE
    le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 72 HOUR)
    AND le.valuenum IS NOT NULL
),
cohort_instability_score AS (
  SELECT
    hadm_id,
    COUNT(DISTINCT lab_name) AS instability_score
  FROM
    labs_first_72h
  WHERE
    is_target_cohort = 1 AND is_abnormal = 1
  GROUP BY
    hadm_id
),
stratified_cohort AS (
  SELECT
    ca.hadm_id,
    ca.hospital_expire_flag,
    DATETIME_DIFF(ca.dischtime, ca.admittime, HOUR) / 24.0 AS los_days,
    COALESCE(cis.instability_score, 0) AS instability_score,
    NTILE(4) OVER (ORDER BY COALESCE(cis.instability_score, 0)) AS instability_quartile
  FROM
    cohort_admissions AS ca
  LEFT JOIN
    cohort_instability_score AS cis
    ON ca.hadm_id = cis.hadm_id
),
stratum_outcomes AS (
  SELECT
    instability_quartile,
    COUNT(hadm_id) AS patient_count,
    AVG(instability_score) AS avg_instability_score,
    AVG(los_days) AS avg_los_days,
    AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate
  FROM
    stratified_cohort
  GROUP BY
    instability_quartile
),
abnormality_rates AS (
  WITH
    patient_lab_abnormal_flags AS (
      SELECT
        hadm_id,
        lab_name,
        is_target_cohort,
        MAX(is_abnormal) AS had_at_least_one_abnormal
      FROM
        labs_first_72h
      GROUP BY
        hadm_id,
        lab_name,
        is_target_cohort
    )
  SELECT
    lab_name,
    SAFE_DIVIDE(
      SUM(CASE WHEN is_target_cohort = 1 THEN had_at_least_one_abnormal ELSE 0 END),
      COUNTIF(is_target_cohort = 1)
    ) AS target_cohort_abnormal_rate,
    SAFE_DIVIDE(
      SUM(CASE WHEN is_target_cohort = 0 THEN had_at_least_one_abnormal ELSE 0 END),
      COUNTIF(is_target_cohort = 0)
    ) AS general_pop_abnormal_rate
  FROM
    patient_lab_abnormal_flags
  GROUP BY
    lab_name
)
SELECT
  s.instability_quartile,
  s.patient_count,
  ROUND(s.avg_instability_score, 2) AS avg_instability_score,
  ROUND(s.avg_los_days, 2) AS avg_los_days,
  ROUND(s.mortality_rate, 3) AS mortality_rate,
  a.lab_name,
  ROUND(a.target_cohort_abnormal_rate, 3) AS target_cohort_abnormal_rate,
  ROUND(a.general_pop_abnormal_rate, 3) AS general_pop_abnormal_rate,
  ROUND(SAFE_DIVIDE(a.target_cohort_abnormal_rate, a.general_pop_abnormal_rate), 2) AS risk_ratio
FROM
  stratum_outcomes AS s
CROSS JOIN
  abnormality_rates AS a
ORDER BY
  s.instability_quartile,
  a.lab_name;
