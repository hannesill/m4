WITH
  ich_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      p.gender,
      p.anchor_age,
      p.dod,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 69 AND 79
      AND (
        (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) IN ('430', '431', '432'))
        OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) IN ('I60', 'I61', 'I62'))
      )
  ),
  complication_and_comorbidity_flags AS (
    SELECT
      d.hadm_id,
      MAX(
        CASE
          WHEN d.icd_code IN ('R68.81', 'R57.0', '995.92', '785.52') THEN 1
          WHEN d.icd_code IN ('R65.21', 'A41.9', '995.92', '038.9') THEN 1
          WHEN d.icd_code IN ('I46.9', '427.5') OR d.icd_code LIKE 'I21%' OR d.icd_code LIKE '410%' THEN 1
          WHEN d.icd_code IN ('J96.00', 'J80', '518.81', '518.82') THEN 1
          WHEN d.icd_code IN ('Z51.11', 'R06.03', 'V58.11', '786.03') THEN 1
          ELSE 0
        END
      ) AS has_major_complication,
      COUNT(DISTINCT d.icd_code) AS diagnosis_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    WHERE
      d.hadm_id IN (SELECT hadm_id FROM ich_cohort)
    GROUP BY
      d.hadm_id
  ),
  patient_outcomes AS (
    SELECT
      c.hadm_id,
      c.dischtime,
      CASE
        WHEN c.hospital_expire_flag = 1 THEN 1
        WHEN c.dod IS NOT NULL AND DATETIME_DIFF(c.dod, c.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS thirty_day_mortality,
      GREATEST(0, DATETIME_DIFF(c.dischtime, c.admittime, DAY)) AS los_days,
      f.has_major_complication,
      (f.has_major_complication * 50) + f.diagnosis_count AS risk_score
    FROM
      ich_cohort AS c
      INNER JOIN complication_and_comorbidity_flags AS f ON c.hadm_id = f.hadm_id
    WHERE
      c.dischtime IS NOT NULL
  ),
  risk_quintiles AS (
    SELECT
      hadm_id,
      thirty_day_mortality,
      los_days,
      has_major_complication,
      risk_score,
      NTILE(5) OVER (ORDER BY risk_score) AS risk_quintile
    FROM
      patient_outcomes
  )
SELECT
  risk_quintile,
  COUNT(hadm_id) AS cohort_size,
  ROUND(AVG(thirty_day_mortality) * 100, 2) AS mortality_rate_30_day_pct,
  ROUND(AVG(has_major_complication) * 100, 2) AS major_complication_rate_pct,
  APPROX_QUANTILES(IF(thirty_day_mortality = 0, los_days, NULL), 2)[OFFSET(1)] AS median_survivor_los_days
FROM
  risk_quintiles
GROUP BY
  risk_quintile
ORDER BY
  risk_quintile;
