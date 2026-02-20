WITH
  ugib_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND (
          icd_code LIKE '578%'
          OR icd_code LIKE '531.0%'
          OR icd_code LIKE '531.2%'
          OR icd_code LIKE '531.4%'
          OR icd_code LIKE '532.0%'
          OR icd_code LIKE '533.0%'
          OR icd_code LIKE '534.0%'
        )
      )
      OR
      (
        icd_version = 10
        AND (
          icd_code IN ('K92.0', 'K92.1', 'K92.2')
          OR icd_code LIKE 'K25.0%'
          OR icd_code LIKE 'K25.2%'
          OR icd_code LIKE 'K26.0%'
          OR icd_code LIKE 'K27.0%'
          OR icd_code LIKE 'K28.0%'
        )
      )
  ),
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      COALESCE(a.deathtime, p.dod) AS death_datetime,
      (
        p.anchor_age + DATETIME_DIFF(
          a.admittime,
          DATETIME(p.anchor_year, 1, 1, 0, 0, 0),
          YEAR
        )
      ) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN ugib_admissions AS ugib ON a.hadm_id = ugib.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + DATETIME_DIFF(
          a.admittime,
          DATETIME(p.anchor_year, 1, 1, 0, 0, 0),
          YEAR
        )
      ) BETWEEN 64 AND 74
  ),
  major_complications AS (
    SELECT
      dx.hadm_id,
      1 AS has_major_complication
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      INNER JOIN patient_cohort pc ON dx.hadm_id = pc.hadm_id
    WHERE
      (
        dx.icd_version = 10 AND dx.icd_code IN ('R68.81', 'R57.0')
      )
      OR (
        dx.icd_version = 9 AND dx.icd_code IN ('995.92', '785.52')
      )
      OR (
        dx.icd_version = 10 AND dx.icd_code IN ('R65.21', 'A41.9')
      )
      OR (
        dx.icd_version = 9 AND dx.icd_code IN ('995.92', '038.9')
      )
      OR (
        dx.icd_version = 10 AND (dx.icd_code LIKE 'I21%' OR dx.icd_code = 'I46.9')
      )
      OR (
        dx.icd_version = 9 AND (dx.icd_code LIKE '410%' OR dx.icd_code = '427.5')
      )
      OR (
        dx.icd_version = 10 AND dx.icd_code IN ('J96.00', 'J80')
      )
      OR (dx.icd_version = 9 AND dx.icd_code IN ('518.81', '518.82'))
    GROUP BY
      dx.hadm_id
  ),
  comorbidity_count AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT icd_code) AS num_diagnoses
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      hadm_id IN (
        SELECT
          hadm_id
        FROM
          patient_cohort
      )
    GROUP BY
      hadm_id
  ),
  cohort_features AS (
    SELECT
      pc.hadm_id,
      GREATEST(
        0,
        DATETIME_DIFF(pc.dischtime, pc.admittime, DAY)
      ) AS los_days,
      CASE
        WHEN pc.death_datetime IS NOT NULL
        AND DATETIME_DIFF(pc.death_datetime, pc.admittime, DAY) <= 30 THEN 1
        ELSE 0
      END AS mortality_30day,
      COALESCE(mc.has_major_complication, 0) AS has_major_complication,
      (COALESCE(cc.num_diagnoses, 0) * 1) + (
        COALESCE(mc.has_major_complication, 0) * 20
      ) AS composite_risk_score
    FROM
      patient_cohort AS pc
      LEFT JOIN major_complications AS mc ON pc.hadm_id = mc.hadm_id
      LEFT JOIN comorbidity_count AS cc ON pc.hadm_id = cc.hadm_id
  ),
  ranked_cohort AS (
    SELECT
      hadm_id,
      los_days,
      mortality_30day,
      has_major_complication,
      composite_risk_score,
      NTILE(5) OVER (
        ORDER BY
          composite_risk_score ASC
      ) AS risk_quintile
    FROM
      cohort_features
  )
SELECT
  risk_quintile,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(AVG(composite_risk_score), 2) AS avg_risk_score,
  ROUND(AVG(mortality_30day) * 100, 2) AS mortality_30day_rate_percent,
  ROUND(
    AVG(has_major_complication) * 100,
    2
  ) AS major_complication_rate_percent,
  APPROX_QUANTILES(
    CASE
      WHEN mortality_30day = 0 THEN los_days
    END,
    2
  )[OFFSET(1)] AS median_survivor_los_days
FROM
  ranked_cohort
GROUP BY
  risk_quintile
ORDER BY
  risk_quintile;
