WITH
  dka_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND ((EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age) BETWEEN 84 AND 94
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE d.hadm_id = a.hadm_id
          AND (
            d.icd_code LIKE '2501%' AND d.icd_version = 9
            OR d.icd_code IN ('E1010', 'E1110', 'E1310') AND d.icd_version = 10
          )
      )
  ),
  meds_first_48h AS (
    SELECT
      pr.hadm_id,
      LOWER(pr.drug) AS drug
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
    INNER JOIN
      dka_cohort AS dc
      ON pr.hadm_id = dc.hadm_id
    WHERE
      pr.starttime <= DATETIME_ADD(dc.admittime, INTERVAL 48 HOUR)
  ),
  patient_metrics AS (
    SELECT
      dc.subject_id,
      dc.hadm_id,
      dc.hospital_expire_flag,
      DATETIME_DIFF(dc.dischtime, dc.admittime, DAY) AS los_days,
      COUNT(DISTINCT m.drug) AS medication_complexity_score,
      (
        COUNT(DISTINCT
          CASE
            WHEN m.drug LIKE '%pril' THEN 'ACEI'
            WHEN m.drug LIKE '%sartan' THEN 'ARB'
            WHEN m.drug IN ('spironolactone', 'amiloride', 'triamterene', 'eplerenone') THEN 'K_SPARING_DIURETIC'
            WHEN m.drug IN ('ibuprofen', 'naproxen', 'ketorolac', 'diclofenac', 'indomethacin', 'meloxicam') THEN 'NSAID'
            WHEN m.drug LIKE 'heparin%' THEN 'HEPARIN'
            WHEN m.drug LIKE 'potassium chloride%' OR m.drug LIKE 'kcl%' OR m.drug LIKE 'k-dur%' OR m.drug LIKE 'klor-con%' THEN 'POTASSIUM_SUPPLEMENT'
            ELSE NULL
          END
        ) >= 2
      ) AS has_hyperkalemia_risk_interaction
    FROM
      dka_cohort AS dc
    LEFT JOIN
      meds_first_48h AS m
      ON dc.hadm_id = m.hadm_id
    GROUP BY
      dc.subject_id,
      dc.hadm_id,
      dc.hospital_expire_flag,
      los_days
  ),
  ranked_metrics AS (
    SELECT
      *,
      PERCENT_RANK() OVER (ORDER BY medication_complexity_score) AS complexity_percentile_rank,
      NTILE(4) OVER (ORDER BY medication_complexity_score DESC) AS complexity_quartile
    FROM
      patient_metrics
  )
SELECT
  CASE
    WHEN has_hyperkalemia_risk_interaction THEN 'Risk Interaction Present'
    ELSE 'Risk Interaction Absent'
  END AS stratum,
  COUNT(hadm_id) AS num_patients,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(complexity_percentile_rank) * 100, 1) AS avg_complexity_percentile,
  ROUND(AVG(los_days), 1) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS INT64)) * 100, 1) AS mortality_rate_percent
FROM
  ranked_metrics
GROUP BY
  has_hyperkalemia_risk_interaction
UNION ALL
SELECT
  'All Patients in Top Quartile' AS stratum,
  COUNT(hadm_id) AS num_patients,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(complexity_percentile_rank) * 100, 1) AS avg_complexity_percentile,
  ROUND(AVG(los_days), 1) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS INT64)) * 100, 1) AS mortality_rate_percent
FROM
  ranked_metrics
WHERE
  complexity_quartile = 1
ORDER BY
  stratum DESC;
