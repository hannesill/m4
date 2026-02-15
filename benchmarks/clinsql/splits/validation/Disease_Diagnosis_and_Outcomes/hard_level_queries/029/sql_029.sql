WITH
  BaseCohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      p.dod AS patient_death_date,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age) BETWEEN 82 AND 92
      AND (
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '480' AND '486')
        OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
      )
  ),
  ComplicationAndBurden AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN
            (icd_version = 9 AND (icd_code LIKE '410%' OR icd_code = '427.5' OR icd_code = '785.52'))
            OR (icd_version = 10 AND (icd_code LIKE 'I21%' OR icd_code LIKE 'I46%' OR icd_code = 'R65.21'))
            THEN 1
          ELSE 0
        END
      ) AS has_cardio_complication,
      MAX(
        CASE
          WHEN
            (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '430' AND '438')
            OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'I60' AND 'I69')
            THEN 1
          ELSE 0
        END
      ) AS has_neuro_complication,
      COUNT(DISTINCT icd_code) AS diagnosis_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      hadm_id IN (
        SELECT hadm_id FROM BaseCohort
      )
    GROUP BY
      hadm_id
  ),
  PatientLevelOutcomes AS (
    SELECT
      b.hadm_id,
      (
        10
        + (c.diagnosis_count - 1) * 3
        + c.has_cardio_complication * 25
        + c.has_neuro_complication * 20
      ) AS risk_score,
      c.has_cardio_complication,
      c.has_neuro_complication,
      CASE
        WHEN b.patient_death_date IS NOT NULL AND b.patient_death_date <= DATETIME_ADD(b.admittime, INTERVAL 30 DAY)
        THEN 1
        ELSE 0
      END AS died_within_30_days,
      CASE
        WHEN b.hospital_expire_flag = 0 THEN DATETIME_DIFF(b.dischtime, b.admittime, DAY)
        ELSE NULL
      END AS survivor_los_days
    FROM
      BaseCohort AS b
      JOIN ComplicationAndBurden AS c ON b.hadm_id = c.hadm_id
  ),
  StratifiedCohort AS (
    SELECT
      hadm_id,
      risk_score,
      died_within_30_days,
      has_cardio_complication,
      has_neuro_complication,
      survivor_los_days,
      NTILE(5) OVER (
        ORDER BY risk_score ASC
      ) AS risk_quintile
    FROM
      PatientLevelOutcomes
  )
SELECT
  risk_quintile,
  COUNT(hadm_id) AS patient_count,
  MIN(risk_score) AS min_risk_score,
  MAX(risk_score) AS max_risk_score,
  ROUND(AVG(died_within_30_days) * 100, 2) AS mortality_rate_30_day_pct,
  ROUND(AVG(has_cardio_complication) * 100, 2) AS cardio_complication_rate_pct,
  ROUND(AVG(has_neuro_complication) * 100, 2) AS neuro_complication_rate_pct,
  APPROX_QUANTILES(survivor_los_days, 100)[OFFSET(50)] AS median_survivor_los_days
FROM
  StratifiedCohort
GROUP BY
  risk_quintile
ORDER BY
  risk_quintile;
