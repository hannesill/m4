WITH first_icu AS (
  SELECT
    i.hadm_id,
    i.stay_id,
    i.intime,
    i.outtime
  FROM `physionet-data.mimiciv_3_1_icu.icustays` AS i
  QUALIFY ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) = 1
),
hf_stays AS (
  SELECT DISTINCT
    icu.stay_id
  FROM first_icu AS icu
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON icu.hadm_id = a.hadm_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON a.subject_id = p.subject_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 70 AND 80
    AND (
      (d.icd_version = 9 AND d.icd_code LIKE '428%')
      OR (d.icd_version = 10 AND d.icd_code LIKE 'I50%')
    )
),
icu_diagnostics AS (
  SELECT
    pe.stay_id,
    COUNT(DISTINCT pe.itemid) AS diagnostic_intensity
  FROM `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
  INNER JOIN first_icu AS icu
    ON pe.stay_id = icu.stay_id
  WHERE
    pe.starttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 72 HOUR)
  GROUP BY
    pe.stay_id
)
SELECT
  CASE
    WHEN hf.stay_id IS NOT NULL
      THEN 'Heart Failure (M, 70-80)'
    ELSE 'General ICU Population'
  END AS cohort,
  COUNT(DISTINCT icu.stay_id) AS num_stays,
  AVG(COALESCE(diag.diagnostic_intensity, 0)) AS avg_diagnostic_intensity,
  APPROX_QUANTILES(COALESCE(diag.diagnostic_intensity, 0), 100)[OFFSET(50)] AS median_diagnostic_intensity,
  APPROX_QUANTILES(COALESCE(diag.diagnostic_intensity, 0), 100)[OFFSET(75)] AS p75_diagnostic_intensity,
  APPROX_QUANTILES(COALESCE(diag.diagnostic_intensity, 0), 100)[OFFSET(95)] AS p95_diagnostic_intensity,
  AVG(DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0) AS avg_icu_los_days,
  AVG(CAST(a.hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_pct
FROM first_icu AS icu
INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  ON icu.hadm_id = a.hadm_id
LEFT JOIN hf_stays AS hf
  ON icu.stay_id = hf.stay_id
LEFT JOIN icu_diagnostics AS diag
  ON icu.stay_id = diag.stay_id
GROUP BY
  cohort
ORDER BY
  cohort DESC;
