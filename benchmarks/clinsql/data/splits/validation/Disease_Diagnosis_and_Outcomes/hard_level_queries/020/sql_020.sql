WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      p.anchor_age,
      a.hospital_expire_flag,
      GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 46 AND 56
  ),
  ami_admissions AS (
    SELECT DISTINCT
      bc.hadm_id,
      bc.anchor_age,
      bc.hospital_expire_flag,
      bc.los_days
    FROM
      base_cohort AS bc
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON bc.hadm_id = d.hadm_id
    WHERE
      (d.icd_version = 9 AND d.icd_code LIKE '410%')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'I21%')
  ),
  complication_counts AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT icd_code) AS complication_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9 AND icd_code IN (
          '995.92',
          '785.52',
          '427.5',
          '518.81',
          '518.82'
        )
      ) OR (
        icd_version = 10 AND icd_code IN (
          'R65.21',
          'A41.9',
          'I46.9',
          'J96.00',
          'J80'
        )
      )
    GROUP BY
      hadm_id
  ),
  cohort_risk_scoring AS (
    SELECT
      ami.hadm_id,
      ami.hospital_expire_flag,
      ami.los_days,
      CASE
        WHEN cc.complication_count > 0 THEN 1
        ELSE 0
      END AS has_major_complication,
      (ami.anchor_age * 1.5) + (COALESCE(cc.complication_count, 0) * 10) AS composite_risk_score
    FROM
      ami_admissions AS ami
      LEFT JOIN complication_counts AS cc
      ON ami.hadm_id = cc.hadm_id
  ),
  risk_strata AS (
    SELECT
      hadm_id,
      hospital_expire_flag,
      los_days,
      has_major_complication,
      composite_risk_score,
      NTILE(5) OVER (
        ORDER BY
          composite_risk_score ASC
      ) AS risk_quintile
    FROM
      cohort_risk_scoring
  )
SELECT
  risk_quintile,
  COUNT(hadm_id) AS patient_count,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS in_hospital_mortality_rate_pct,
  ROUND(AVG(CAST(has_major_complication AS FLOAT64)) * 100, 2) AS major_complication_rate_pct,
  APPROX_QUANTILES(
    IF(hospital_expire_flag = 0, los_days, NULL),
    2
  )[OFFSET(1)] AS median_survivor_los_days
FROM
  risk_strata
GROUP BY
  risk_quintile
ORDER BY
  risk_quintile;
