WITH
patient_admissions AS (
  SELECT
    p.subject_id,
    p.dod,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag,
    p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 75 AND 85
),
copd_cohort AS (
  SELECT DISTINCT
    pa.*
  FROM
    patient_admissions AS pa
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON pa.hadm_id = dx.hadm_id
  WHERE
    dx.icd_code IN ('49121', 'J441')
),
complications_agg AS (
  SELECT
    c.hadm_id,
    COUNT(DISTINCT
      CASE
        WHEN dx.icd_code IN ('R6881', 'R570', '99592', '78552') THEN 'mof'
        WHEN dx.icd_code IN ('R6521', 'A419', '0389') THEN 'sepsis'
        WHEN dx.icd_version = 10 AND STARTS_WITH(dx.icd_code, 'I21') THEN 'mi'
        WHEN dx.icd_version = 9 AND STARTS_WITH(dx.icd_code, '410') THEN 'mi'
        WHEN dx.icd_code IN ('I469', '4275') THEN 'mi_comp'
        WHEN dx.icd_code IN ('J9600', 'J80', '51881', '51882') THEN 'arf'
        ELSE NULL
      END
    ) AS num_major_complications
  FROM
    copd_cohort AS c
  LEFT JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON c.hadm_id = dx.hadm_id
  GROUP BY
    c.hadm_id
),
risk_calculation AS (
  SELECT
    c.*,
    COALESCE(ca.num_major_complications, 0) AS num_major_complications,
    ( (c.age_at_admission - 75) * 5 ) + (LEAST(COALESCE(ca.num_major_complications, 0), 2) * 25) AS risk_score,
    DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
    CASE
      WHEN c.hospital_expire_flag = 1 THEN 1
      WHEN c.dod IS NOT NULL AND c.dod <= DATE_ADD(c.dischtime, INTERVAL 90 DAY) THEN 1
      ELSE 0
    END AS mortality_90day_flag
  FROM
    copd_cohort AS c
  LEFT JOIN
    complications_agg AS ca
    ON c.hadm_id = ca.hadm_id
  WHERE
    c.dischtime IS NOT NULL
),
quartiled_cohort AS (
  SELECT
    *,
    NTILE(4) OVER (ORDER BY risk_score) AS risk_quartile
  FROM
    risk_calculation
),
broader_pop_stats AS (
  SELECT
    ROUND(AVG(
      CASE
        WHEN pa.hospital_expire_flag = 1 THEN 1.0
        WHEN pa.dod IS NOT NULL AND pa.dod <= DATE_ADD(pa.dischtime, INTERVAL 90 DAY) THEN 1.0
        ELSE 0.0
      END
    ) * 100, 2) AS broader_pop_90day_mortality_pct
  FROM
    patient_admissions AS pa
  WHERE pa.dischtime IS NOT NULL
)
SELECT
  q.risk_quartile,
  COUNT(q.hadm_id) AS total_admissions,
  ROUND(AVG(q.risk_score), 1) AS avg_risk_score,
  ROUND(AVG(q.mortality_90day_flag) * 100, 2) AS cohort_mortality_90day_rate_pct,
  b.broader_pop_90day_mortality_pct,
  ROUND(AVG(CASE WHEN q.num_major_complications > 0 THEN 1.0 ELSE 0.0 END) * 100, 2) AS major_complication_rate_pct,
  APPROX_QUANTILES(IF(q.mortality_90day_flag = 0, q.los_days, NULL), 100)[OFFSET(50)] AS median_survivor_los_days
FROM
  quartiled_cohort AS q,
  broader_pop_stats AS b
GROUP BY
  q.risk_quartile,
  b.broader_pop_90day_mortality_pct
ORDER BY
  q.risk_quartile;
