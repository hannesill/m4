WITH
ards_admissions AS (
  SELECT
    adm.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime,
    adm.hospital_expire_flag,
    p.gender,
    p.anchor_year,
    p.anchor_age
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON adm.subject_id = p.subject_id
  WHERE adm.hadm_id IN (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE 'J80%'
      OR icd_code = '518.82'
  )
),
target_cohort AS (
  SELECT
    hadm_id,
    admittime,
    dischtime,
    hospital_expire_flag
  FROM ards_admissions
  WHERE
    gender = 'M'
    AND (EXTRACT(YEAR FROM admittime) - anchor_year) + anchor_age BETWEEN 71 AND 81
),
critical_labs AS (
  SELECT
    lab.hadm_id,
    lab.charttime,
    CASE
      WHEN lab.itemid = 50983 THEN 'Sodium'
      WHEN lab.itemid = 50971 THEN 'Potassium'
      WHEN lab.itemid = 50912 THEN 'Creatinine'
      WHEN lab.itemid = 51301 THEN 'WBC'
      WHEN lab.itemid = 51265 THEN 'Platelets'
      WHEN lab.itemid = 50813 THEN 'Lactate'
      WHEN lab.itemid = 50820 THEN 'pH, Arterial'
      ELSE 'Other'
    END AS lab_name
  FROM `physionet-data.mimiciv_3_1_hosp.labevents` AS lab
  WHERE lab.hadm_id IS NOT NULL AND lab.valuenum IS NOT NULL
  AND (
    (lab.itemid = 50983 AND (lab.valuenum < 120 OR lab.valuenum > 160))
    OR (lab.itemid = 50971 AND (lab.valuenum < 2.5 OR lab.valuenum > 6.5))
    OR (lab.itemid = 50912 AND lab.valuenum > 4.0)
    OR (lab.itemid = 51301 AND (lab.valuenum < 1.0 OR lab.valuenum > 50.0))
    OR (lab.itemid = 51265 AND lab.valuenum < 20)
    OR (lab.itemid = 50813 AND lab.valuenum > 4.0)
    OR (lab.itemid = 50820 AND (lab.valuenum < 7.20 OR lab.valuenum > 7.60))
  )
),
cohort_instability_scores AS (
  SELECT
    cohort.hadm_id,
    cohort.hospital_expire_flag,
    TIMESTAMP_DIFF(cohort.dischtime, cohort.admittime, HOUR) / 24.0 AS los_days,
    COUNT(cl.hadm_id) AS instability_score
  FROM target_cohort AS cohort
  LEFT JOIN critical_labs AS cl
    ON cohort.hadm_id = cl.hadm_id
    AND cl.charttime BETWEEN cohort.admittime AND TIMESTAMP_ADD(cohort.admittime, INTERVAL 72 HOUR)
  GROUP BY cohort.hadm_id, cohort.hospital_expire_flag, los_days
),
cohort_percentiles AS (
  SELECT
    APPROX_QUANTILES(instability_score, 100)[OFFSET(90)] AS p90_instability_score
  FROM cohort_instability_scores
),
top_tier_outcomes AS (
  SELECT
    COUNT(scores.hadm_id) AS top_tier_patient_count,
    AVG(scores.los_days) AS top_tier_avg_los_days,
    AVG(CAST(scores.hospital_expire_flag AS FLOAT64)) AS top_tier_mortality_rate
  FROM cohort_instability_scores AS scores
  CROSS JOIN cohort_percentiles AS p
  WHERE scores.instability_score >= p.p90_instability_score
),
top_tier_lab_freq AS (
  SELECT
    cl.lab_name,
    COUNT(*) AS critical_event_count
  FROM cohort_instability_scores AS scores
  INNER JOIN target_cohort AS cohort ON scores.hadm_id = cohort.hadm_id
  INNER JOIN critical_labs AS cl ON scores.hadm_id = cl.hadm_id
  CROSS JOIN cohort_percentiles AS p
  WHERE
    scores.instability_score >= p.p90_instability_score
    AND cl.charttime BETWEEN cohort.admittime AND TIMESTAMP_ADD(cohort.admittime, INTERVAL 72 HOUR)
  GROUP BY cl.lab_name
),
general_pop_lab_freq AS (
  SELECT
    cl.lab_name,
    COUNT(*) AS critical_event_count,
    COUNT(DISTINCT adm.hadm_id) AS patient_count
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  INNER JOIN critical_labs AS cl
    ON adm.hadm_id = cl.hadm_id
    AND cl.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 72 HOUR)
  GROUP BY cl.lab_name
),
general_pop_total_count AS (
  SELECT COUNT(DISTINCT hadm_id) AS total_patients
  FROM `physionet-data.mimiciv_3_1_hosp.admissions`
)
SELECT
  p.p90_instability_score,
  outcomes.top_tier_avg_los_days,
  outcomes.top_tier_mortality_rate,
  COALESCE(top_tier.lab_name, general.lab_name) AS lab_test_name,
  COALESCE(top_tier.critical_event_count, 0) AS critical_events_in_top_tier,
  SAFE_DIVIDE(COALESCE(top_tier.critical_event_count, 0), outcomes.top_tier_patient_count) AS critical_event_rate_top_tier,
  COALESCE(general.critical_event_count, 0) AS critical_events_in_general_pop,
  SAFE_DIVIDE(COALESCE(general.critical_event_count, 0), gpc.total_patients) AS critical_event_rate_general_pop
FROM top_tier_lab_freq AS top_tier
FULL OUTER JOIN general_pop_lab_freq AS general
  ON top_tier.lab_name = general.lab_name
CROSS JOIN cohort_percentiles AS p
CROSS JOIN top_tier_outcomes AS outcomes
CROSS JOIN general_pop_total_count AS gpc
ORDER BY critical_events_in_top_tier DESC, lab_test_name;
