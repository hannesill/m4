WITH
cohort_admissions AS (
  SELECT
    a.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON a.subject_id = p.subject_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 89 AND 99
    AND EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      WHERE dx.hadm_id = a.hadm_id
      AND (
        (dx.icd_version = 9 AND (dx.icd_code LIKE '578%' OR dx.icd_code = '569.3'))
        OR
        (dx.icd_version = 10 AND dx.icd_code IN ('K92.1', 'K92.2', 'K62.5'))
      )
    )
),
critical_labs AS (
  SELECT
    hadm_id,
    charttime,
    itemid,
    CASE
      WHEN itemid = 50971 AND (valuenum < 3.0 OR valuenum > 5.5) THEN 1
      WHEN itemid = 50983 AND (valuenum < 125 OR valuenum > 150) THEN 1
      WHEN itemid = 50912 AND valuenum > 2.0 THEN 1
      WHEN itemid = 51003 AND valuenum > 0.1 THEN 1
      WHEN itemid = 50931 AND (valuenum < 60 OR valuenum > 300) THEN 1
      WHEN itemid = 51006 AND valuenum > 40 THEN 1
      ELSE 0
    END AS is_critical
  FROM
    `physionet-data.mimiciv_3_1_hosp.labevents`
  WHERE
    hadm_id IS NOT NULL
    AND valuenum IS NOT NULL
    AND itemid IN (
      50971,
      50983,
      50912,
      51003,
      50931,
      51006
    )
),
cohort_instability AS (
  SELECT
    ca.subject_id,
    ca.hadm_id,
    ca.hospital_expire_flag,
    ca.admittime,
    ca.dischtime,
    SUM(cl.is_critical) AS instability_score,
    COUNT(cl.itemid) AS total_labs_in_window
  FROM
    cohort_admissions AS ca
  INNER JOIN
    critical_labs AS cl
    ON ca.hadm_id = cl.hadm_id
  WHERE
    cl.charttime BETWEEN ca.admittime AND DATETIME_ADD(ca.admittime, INTERVAL 72 HOUR)
  GROUP BY
    ca.subject_id,
    ca.hadm_id,
    ca.hospital_expire_flag,
    ca.admittime,
    ca.dischtime
),
cohort_ranked AS (
  SELECT
    *,
    DATETIME_DIFF(dischtime, admittime, HOUR) / 24.0 AS los_days,
    NTILE(5) OVER (ORDER BY instability_score) AS instability_quintile
  FROM
    cohort_instability
),
general_population_critical_rate AS (
  SELECT
    SAFE_DIVIDE(SUM(cl.is_critical), COUNT(cl.itemid)) AS general_critical_rate
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  INNER JOIN
    critical_labs AS cl
    ON a.hadm_id = cl.hadm_id
  WHERE
    cl.charttime BETWEEN a.admittime AND DATETIME_ADD(a.admittime, INTERVAL 72 HOUR)
)
SELECT
  r.instability_quintile,
  COUNT(DISTINCT r.hadm_id) AS num_patients,
  MIN(r.instability_score) AS min_score_in_quintile,
  MAX(r.instability_score) AS max_score_in_quintile,
  ROUND(AVG(r.instability_score), 2) AS avg_instability_score,
  ROUND(AVG(r.los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(r.hospital_expire_flag AS FLOAT64)), 3) AS mortality_rate,
  ROUND(SAFE_DIVIDE(SUM(r.instability_score), SUM(r.total_labs_in_window)), 3) AS cohort_quintile_critical_rate,
  ROUND(g.general_critical_rate, 3) AS general_population_critical_rate
FROM
  cohort_ranked AS r,
  general_population_critical_rate AS g
GROUP BY
  r.instability_quintile,
  g.general_critical_rate
ORDER BY
  r.instability_quintile;
