WITH
  ich_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432'))
      OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62'))
  ),
  base_cohorts AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.anchor_age,
      CASE
        WHEN ich.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS is_ich_case
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
      LEFT JOIN ich_admissions AS ich ON a.hadm_id = ich.hadm_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 74 AND 84
  ),
  lab_definitions AS (
    SELECT 50983 AS itemid, 'Sodium' AS lab_name, 135 AS lower_normal, 145 AS upper_normal UNION ALL
    SELECT 50971 AS itemid, 'Potassium' AS lab_name, 3.5 AS lower_normal, 5.2 AS upper_normal UNION ALL
    SELECT 50912 AS itemid, 'Creatinine' AS lab_name, 0.6 AS lower_normal, 1.2 AS upper_normal UNION ALL
    SELECT 50882 AS itemid, 'Bicarbonate' AS lab_name, 22 AS lower_normal, 28 AS upper_normal UNION ALL
    SELECT 51301 AS itemid, 'WBC' AS lab_name, 4.0 AS lower_normal, 11.0 AS upper_normal UNION ALL
    SELECT 51265 AS itemid, 'Platelets' AS lab_name, 150 AS lower_normal, 450 AS upper_normal UNION ALL
    SELECT 51222 AS itemid, 'Hemoglobin' AS lab_name, 12.0 AS lower_normal, 16.0 AS upper_normal
  ),
  abnormal_labs_first_72h AS (
    SELECT
      bc.hadm_id,
      bc.is_ich_case,
      ld.lab_name
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN base_cohorts AS bc ON le.hadm_id = bc.hadm_id
      INNER JOIN lab_definitions AS ld ON le.itemid = ld.itemid
    WHERE
      le.charttime BETWEEN bc.admittime AND DATETIME_ADD(bc.admittime, INTERVAL 72 HOUR)
      AND le.valuenum IS NOT NULL
      AND (le.valuenum < ld.lower_normal OR le.valuenum > ld.upper_normal)
  ),
  patient_scores AS (
    SELECT
      bc.hadm_id,
      bc.subject_id,
      bc.is_ich_case,
      bc.hospital_expire_flag,
      DATETIME_DIFF(bc.dischtime, bc.admittime, DAY) AS los_days,
      COALESCE(agg_labs.lab_instability_score, 0) AS lab_instability_score
    FROM
      base_cohorts AS bc
      LEFT JOIN (
        SELECT
          hadm_id,
          COUNT(DISTINCT lab_name) AS lab_instability_score
        FROM
          abnormal_labs_first_72h
        GROUP BY
          hadm_id
      ) AS agg_labs ON bc.hadm_id = agg_labs.hadm_id
  ),
  ich_cohort_ranked AS (
    SELECT
      hadm_id,
      los_days,
      hospital_expire_flag,
      lab_instability_score,
      NTILE(5) OVER (ORDER BY lab_instability_score) AS instability_quintile,
      PERCENT_RANK() OVER (ORDER BY lab_instability_score) AS percentile_rank
    FROM
      patient_scores
    WHERE
      is_ich_case = 1
  ),
  ich_quintile_outcomes AS (
    SELECT
      instability_quintile,
      COUNT(*) AS num_patients,
      MIN(lab_instability_score) AS min_score_in_quintile,
      MAX(lab_instability_score) AS max_score_in_quintile,
      AVG(lab_instability_score) AS avg_instability_score,
      AVG(los_days) AS avg_los_days,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent
    FROM
      ich_cohort_ranked
    GROUP BY
      instability_quintile
  ),
  cohort_counts AS (
    SELECT
      is_ich_case,
      COUNT(DISTINCT hadm_id) AS total_patients
    FROM
      base_cohorts
    GROUP BY
      is_ich_case
  ),
  critical_lab_rates AS (
    SELECT
      ab.lab_name,
      (COUNT(DISTINCT CASE WHEN ab.is_ich_case = 1 THEN ab.hadm_id END) / MAX(CASE WHEN cc.is_ich_case = 1 THEN cc.total_patients END)) * 100 AS ich_case_abnormality_percent,
      (COUNT(DISTINCT CASE WHEN ab.is_ich_case = 0 THEN ab.hadm_id END) / MAX(CASE WHEN cc.is_ich_case = 0 THEN cc.total_patients END)) * 100 AS control_group_abnormality_percent
    FROM
      abnormal_labs_first_72h AS ab
      CROSS JOIN cohort_counts AS cc
    GROUP BY
      ab.lab_name
  )
SELECT
  q.instability_quintile,
  q.num_patients,
  q.min_score_in_quintile,
  q.max_score_in_quintile,
  ROUND(q.avg_instability_score, 2) AS avg_instability_score,
  ROUND(q.avg_los_days, 1) AS avg_los_days,
  ROUND(q.mortality_rate_percent, 2) AS mortality_rate_percent,
  (
    SELECT
      ARRAY_AGG(
        STRUCT(
          r.lab_name,
          ROUND(r.ich_case_abnormality_percent, 2) AS ich_case_abnormality_percent,
          ROUND(r.control_group_abnormality_percent, 2) AS control_group_abnormality_percent,
          ROUND(r.ich_case_abnormality_percent - r.control_group_abnormality_percent, 2) AS difference_percent
        ) ORDER BY r.lab_name
      )
    FROM
      critical_lab_rates AS r
  ) AS lab_abnormality_rate_comparison
FROM
  ich_quintile_outcomes AS q
ORDER BY
  q.instability_quintile;
