WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag,
    (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
),
aged_cohort AS (
  SELECT
    *
  FROM
    patient_cohort
  WHERE
    age_at_admission BETWEEN 81 AND 91
),
aki_diagnoses AS (
  SELECT DISTINCT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND STARTS_WITH(icd_code, '584'))
    OR (icd_version = 10 AND STARTS_WITH(icd_code, 'N17'))
),
final_cohort AS (
  SELECT
    ac.subject_id,
    ac.hadm_id,
    ac.admittime,
    ac.dischtime,
    ac.hospital_expire_flag,
    ac.age_at_admission
  FROM
    aged_cohort AS ac
  JOIN
    aki_diagnoses AS ad
    ON ac.hadm_id = ad.hadm_id
),
medications_with_flags AS (
  SELECT
    p.hadm_id,
    p.drug,
    p.route,
    CASE
      WHEN LOWER(p.drug) LIKE '%morphine%'
      OR LOWER(p.drug) LIKE '%fentanyl%'
      OR LOWER(p.drug) LIKE '%hydromorphone%'
      OR LOWER(p.drug) LIKE '%oxycodone%'
      OR LOWER(p.drug) LIKE '%lorazepam%'
      OR LOWER(p.drug) LIKE '%midazolam%'
      OR LOWER(p.drug) LIKE '%diazepam%'
      OR LOWER(p.drug) LIKE '%propofol%'
      OR LOWER(p.drug) LIKE '%diphenhydramine%'
      OR LOWER(p.drug) LIKE '%zolpidem%' THEN 1
      ELSE 0
    END AS is_cns_depressant,
    CASE
      WHEN LOWER(p.drug) LIKE '%ibuprofen%'
      OR LOWER(p.drug) LIKE '%naproxen%'
      OR LOWER(p.drug) LIKE '%ketorolac%'
      OR LOWER(p.drug) LIKE '%gentamicin%'
      OR LOWER(p.drug) LIKE '%tobramycin%'
      OR LOWER(p.drug) LIKE '%amikacin%'
      OR LOWER(p.drug) LIKE '%vancomycin%'
      OR LOWER(p.drug) LIKE '%furosemide%'
      OR LOWER(p.drug) LIKE '%lisinopril%'
      OR LOWER(p.drug) LIKE '%losartan%' THEN 1
      ELSE 0
    END AS is_nephrotoxic
  FROM
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS p
  WHERE
    p.hadm_id IN (
      SELECT hadm_id FROM final_cohort
    )
),
patient_level_summary AS (
  SELECT
    m.hadm_id,
    (COUNT(DISTINCT m.drug) + COUNT(DISTINCT m.route)) AS medication_complexity_score,
    MAX(m.is_cns_depressant) AS has_cns_depressant,
    MAX(m.is_nephrotoxic) AS has_nephrotoxic
  FROM
    medications_with_flags AS m
  GROUP BY
    m.hadm_id
),
ranked_outcomes AS (
  SELECT
    pls.hadm_id,
    fc.hospital_expire_flag,
    DATETIME_DIFF(fc.dischtime, fc.admittime, DAY) AS los_days,
    pls.medication_complexity_score,
    CASE
      WHEN pls.has_cns_depressant = 1 AND pls.has_nephrotoxic = 1 THEN 'CNS Depression + Nephrotoxic'
      ELSE 'General AKI Cohort'
    END AS risk_category,
    PERCENT_RANK() OVER (ORDER BY pls.medication_complexity_score) AS complexity_percentile_rank
  FROM
    patient_level_summary AS pls
  JOIN
    final_cohort AS fc
    ON pls.hadm_id = fc.hadm_id
)
SELECT
  risk_category,
  COUNT(hadm_id) AS num_patients,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  APPROX_QUANTILES(medication_complexity_score, 4) AS complexity_score_quartiles,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_pct,
  COUNTIF(complexity_percentile_rank >= 0.75) AS top_quartile_patient_count,
  ROUND(AVG(IF(complexity_percentile_rank >= 0.75, los_days, NULL)), 2) AS top_quartile_avg_los,
  ROUND(AVG(IF(complexity_percentile_rank >= 0.75, CAST(hospital_expire_flag AS FLOAT64), NULL)) * 100, 2) AS top_quartile_mortality_rate_pct
FROM
  ranked_outcomes
GROUP BY
  risk_category
ORDER BY
  risk_category DESC;
