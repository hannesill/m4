WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 85 AND 95
  ),
  asthma_admissions AS (
    SELECT DISTINCT
      bc.subject_id,
      bc.hadm_id,
      bc.admittime,
      bc.dischtime,
      bc.hospital_expire_flag
    FROM
      base_cohort AS bc
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON bc.hadm_id = d.hadm_id
    WHERE
      d.icd_code IN ('49301', '49311', '49321', '49391')
      OR d.icd_code IN ('J4521', 'J4531', 'J4541', 'J4551', 'J45901')
  ),
  patient_features AS (
    SELECT
      aa.hadm_id,
      aa.hospital_expire_flag,
      DATETIME_DIFF(aa.dischtime, aa.admittime, DAY) AS los,
      SUM(
        CASE
          WHEN d.icd_code LIKE '428%' OR d.icd_code LIKE 'I50%' THEN 25
          WHEN d.icd_code LIKE '585%' OR d.icd_code LIKE 'N18%' THEN 20
          WHEN d.icd_code = '42731' OR d.icd_code LIKE 'I48%' THEN 15
          WHEN d.icd_code LIKE '250%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' THEN 10
          ELSE 0
        END
      ) AS risk_score,
      MAX(
        CASE
          WHEN d.icd_code LIKE '410%'
          OR d.icd_code LIKE 'I21%'
          OR d.icd_code LIKE 'I22%'
          OR d.icd_code LIKE '430%'
          OR d.icd_code LIKE '431%'
          OR d.icd_code LIKE 'I60%'
          OR d.icd_code LIKE 'I61%'
          OR d.icd_code LIKE 'I63%' THEN 1
          ELSE 0
        END
      ) AS has_cardiac_complication,
      MAX(
        CASE
          WHEN d.icd_code IN ('2930', '2931', '78009', '3483', 'F05', 'R410', 'G9340', 'G9341') THEN 1
          ELSE 0
        END
      ) AS has_neuro_complication
    FROM
      asthma_admissions AS aa
      LEFT JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON aa.hadm_id = d.hadm_id
    GROUP BY
      aa.hadm_id,
      aa.hospital_expire_flag,
      aa.admittime,
      aa.dischtime
  ),
  stratified_patients AS (
    SELECT
      pf.hospital_expire_flag,
      pf.has_cardiac_complication,
      pf.has_neuro_complication,
      CASE
        WHEN pf.hospital_expire_flag = 0 THEN pf.los
        ELSE NULL
      END AS survivor_los,
      NTILE(4) OVER (
        ORDER BY
          pf.risk_score
      ) AS risk_quartile
    FROM
      patient_features AS pf
  )
SELECT
  risk_quartile,
  COUNT(*) AS total_patients,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS in_hospital_mortality_rate,
  ROUND(AVG(has_cardiac_complication) * 100, 2) AS cardiovascular_complication_rate,
  ROUND(AVG(has_neuro_complication) * 100, 2) AS neurologic_complication_rate,
  APPROX_QUANTILES(survivor_los, 2)[OFFSET(1)] AS median_survivor_los_days
FROM
  stratified_patients
GROUP BY
  risk_quartile
ORDER BY
  risk_quartile;
