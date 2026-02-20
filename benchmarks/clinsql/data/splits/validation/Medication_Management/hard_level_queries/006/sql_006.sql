WITH
patient_cohort AS (
  SELECT
    p.subject_id,
    ad.hadm_id,
    ad.admittime,
    ad.dischtime,
    ad.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS ad
    ON p.subject_id = ad.subject_id
  WHERE
    p.gender = 'M'
    AND (DATETIME_DIFF(ad.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) BETWEEN 37 AND 47
),
postop_admissions AS (
  SELECT DISTINCT
    pc.hadm_id
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
    ON pc.hadm_id = proc.hadm_id
),
final_cohort_admissions AS (
  SELECT DISTINCT
    pa.hadm_id
  FROM
    postop_admissions AS pa
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON pa.hadm_id = icu.hadm_id
),
meds_first_72h AS (
  SELECT
    pr.hadm_id,
    pr.drug,
    pr.route,
    CASE
      WHEN LOWER(pr.drug) LIKE '%norepinephrine%' OR LOWER(pr.drug) LIKE '%epinephrine%' OR LOWER(pr.drug) LIKE '%vasopressin%' OR LOWER(pr.drug) LIKE '%phenylephrine%' OR LOWER(pr.drug) LIKE '%dopamine%' OR LOWER(pr.drug) LIKE '%dobutamine%' THEN 'vasoactive'
      WHEN LOWER(pr.drug) LIKE '%heparin%' OR LOWER(pr.drug) LIKE '%warfarin%' OR LOWER(pr.drug) LIKE '%enoxaparin%' OR LOWER(pr.drug) LIKE '%rivaroxaban%' OR LOWER(pr.drug) LIKE '%apixaban%' OR LOWER(pr.drug) LIKE '%argatroban%' THEN 'anticoagulant'
      WHEN LOWER(pr.drug) LIKE '%insulin%' THEN 'insulin'
      WHEN LOWER(pr.drug) LIKE '%vancomycin%' OR LOWER(pr.drug) LIKE '%meropenem%' OR LOWER(pr.drug) LIKE '%piperacillin%' OR LOWER(pr.drug) LIKE '%tazobactam%' THEN 'broad_spectrum_antibiotic'
      ELSE NULL
    END AS high_risk_class
  FROM
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS ad ON pr.hadm_id = ad.hadm_id
  WHERE
    pr.hadm_id IN (SELECT hadm_id FROM final_cohort_admissions)
    AND pr.starttime <= DATETIME_ADD(ad.admittime, INTERVAL 72 HOUR)
),
medication_complexity AS (
  SELECT
    hadm_id,
    (
      (COUNT(DISTINCT drug) * 1.0) +
      (COUNT(DISTINCT CASE WHEN high_risk_class IS NOT NULL THEN drug END) * 2.0) +
      (COUNT(DISTINCT route) * 0.5)
    ) AS complexity_score
  FROM
    meds_first_72h
  GROUP BY
    hadm_id
),
readmission_info AS (
  SELECT
    subject_id,
    hadm_id,
    dischtime,
    LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions`
),
cohort_with_outcomes AS (
  SELECT
    fc.hadm_id,
    ad.subject_id,
    mc.complexity_score,
    DATETIME_DIFF(ad.dischtime, ad.admittime, DAY) AS los_days,
    ad.hospital_expire_flag,
    CASE
      WHEN DATETIME_DIFF(ri.next_admittime, ad.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
      ELSE 0
    END AS readmission_30d_flag
  FROM
    final_cohort_admissions AS fc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS ad
    ON fc.hadm_id = ad.hadm_id
  LEFT JOIN
    medication_complexity AS mc
    ON fc.hadm_id = mc.hadm_id
  LEFT JOIN
    readmission_info AS ri
    ON fc.hadm_id = ri.hadm_id
),
ranked_cohort AS (
  SELECT
    hadm_id,
    COALESCE(complexity_score, 0) AS complexity_score,
    los_days,
    hospital_expire_flag,
    readmission_30d_flag,
    NTILE(5) OVER (ORDER BY COALESCE(complexity_score, 0) ASC) AS complexity_quintile
  FROM
    cohort_with_outcomes
)
SELECT
  complexity_quintile,
  COUNT(hadm_id) AS num_patients,
  MIN(complexity_score) AS min_complexity_score,
  ROUND(AVG(complexity_score), 2) AS avg_complexity_score,
  MAX(complexity_score) AS max_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(readmission_30d_flag) * 100, 2) AS readmission_30d_rate_pct
FROM
  ranked_cohort
GROUP BY
  complexity_quintile
ORDER BY
  complexity_quintile;
