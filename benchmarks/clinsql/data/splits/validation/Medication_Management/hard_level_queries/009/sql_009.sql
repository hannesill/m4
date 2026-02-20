WITH
  aki_cohort_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 84 AND 94
      AND a.hadm_id IN (
        SELECT DISTINCT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          icd_code LIKE '584%' OR icd_code LIKE 'N17%'
      )
  ),
  cohort_outcomes AS (
    SELECT
      hadm_id,
      subject_id,
      admittime,
      dischtime,
      hospital_expire_flag,
      DATETIME_DIFF(dischtime, admittime, DAY) AS los_days,
      LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime,
      CASE
        WHEN DATETIME_DIFF(LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime), dischtime, DAY) <= 30
        THEN 1
        ELSE 0
      END AS is_readmitted_30d
    FROM
      aki_cohort_admissions
  ),
  medication_features AS (
    SELECT
      pr.hadm_id,
      COUNT(DISTINCT pr.drug) AS unique_drug_count,
      COUNT(DISTINCT pr.route) AS unique_route_count,
      COUNT(
        CASE
          WHEN
            LOWER(pr.drug) LIKE '%heparin%' OR LOWER(pr.drug) LIKE '%warfarin%' OR LOWER(pr.drug) LIKE '%enoxaparin%'
            OR LOWER(pr.drug) LIKE '%insulin%'
            OR LOWER(pr.drug) LIKE '%morphine%' OR LOWER(pr.drug) LIKE '%fentanyl%' OR LOWER(pr.drug) LIKE '%hydromorphone%' OR LOWER(pr.drug) LIKE '%oxycodone%'
            OR LOWER(pr.drug) LIKE '%norepinephrine%' OR LOWER(pr.drug) LIKE '%vasopressin%' OR LOWER(pr.drug) LIKE '%epinephrine%'
            THEN 1
          ELSE NULL
        END
      ) AS high_risk_drug_admin_count,
      MAX(CASE WHEN LOWER(pr.drug) LIKE '%heparin%' OR LOWER(pr.drug) LIKE '%warfarin%' OR LOWER(pr.drug) LIKE '%enoxaparin%' THEN 1 ELSE 0 END) AS has_anticoagulant,
      MAX(CASE WHEN LOWER(pr.drug) LIKE '%morphine%' OR LOWER(pr.drug) LIKE '%fentanyl%' OR LOWER(pr.drug) LIKE '%hydromorphone%' OR LOWER(pr.drug) LIKE '%oxycodone%' THEN 1 ELSE 0 END) AS has_opioid
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      INNER JOIN cohort_outcomes AS co
        ON pr.hadm_id = co.hadm_id
    GROUP BY
      pr.hadm_id
  ),
  patient_level_scores AS (
    SELECT
      co.hadm_id,
      co.los_days,
      co.hospital_expire_flag,
      co.is_readmitted_30d,
      COALESCE(mf.unique_drug_count, 0)
      + (COALESCE(mf.unique_route_count, 0) * 0.5)
      + (COALESCE(mf.high_risk_drug_admin_count, 0) * 1.5) AS medication_complexity_score,
      CASE WHEN mf.has_anticoagulant = 1 AND mf.has_opioid = 1 THEN 1 ELSE 0 END AS interaction_anticoag_opioid
    FROM
      cohort_outcomes AS co
      LEFT JOIN medication_features AS mf
        ON co.hadm_id = mf.hadm_id
  ),
  ranked_patients AS (
    SELECT
      *,
      PERCENT_RANK() OVER (ORDER BY medication_complexity_score) AS percentile_rank,
      NTILE(5) OVER (ORDER BY medication_complexity_score) AS score_quintile
    FROM
      patient_level_scores
  )
SELECT
  score_quintile,
  COUNT(hadm_id) AS num_admissions,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(CAST(is_readmitted_30d AS FLOAT64)) * 100, 2) AS readmission_rate_30d_percent,
  SUM(interaction_anticoag_opioid) AS count_with_anticoag_opioid_interaction
FROM
  ranked_patients
GROUP BY
  score_quintile
ORDER BY
  score_quintile;
