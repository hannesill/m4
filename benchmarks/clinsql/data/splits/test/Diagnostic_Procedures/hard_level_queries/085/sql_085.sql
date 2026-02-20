WITH first_icu_stays AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    i.stay_id,
    a.admittime,
    a.dischtime,
    i.intime,
    i.outtime,
    a.hospital_expire_flag,
    ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS icu_stay_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS i
    ON a.hadm_id = i.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 87 AND 97
),
cohort_stays AS (
  SELECT
    fs.hadm_id,
    fs.stay_id,
    fs.intime,
    fs.outtime,
    fs.hospital_expire_flag
  FROM
    first_icu_stays AS fs
  WHERE
    fs.icu_stay_rank = 1
    AND EXISTS (
      SELECT
        1
      FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      WHERE
        dx.hadm_id = fs.hadm_id
        AND (
          (dx.icd_version = 9 AND (dx.icd_code LIKE '5781%' OR dx.icd_code LIKE '5693%'))
          OR (dx.icd_version = 10 AND (dx.icd_code LIKE 'K921%' OR dx.icd_code LIKE 'K922%' OR dx.icd_code LIKE 'K625%'))
        )
    )
),
diagnostic_load AS (
  SELECT
    cs.stay_id,
    cs.intime,
    cs.outtime,
    cs.hospital_expire_flag,
    COUNT(DISTINCT pe.itemid) AS diagnostic_load_48hr
  FROM
    cohort_stays AS cs
  LEFT JOIN
    `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
    ON cs.stay_id = pe.stay_id
    AND pe.starttime BETWEEN cs.intime AND DATETIME_ADD(cs.intime, INTERVAL 48 HOUR)
  GROUP BY
    cs.stay_id,
    cs.intime,
    cs.outtime,
    cs.hospital_expire_flag
),
quintile_boundaries AS (
  SELECT
    APPROX_QUANTILES(diagnostic_load_48hr, 100)[OFFSET(20)] AS p20,
    APPROX_QUANTILES(diagnostic_load_48hr, 100)[OFFSET(40)] AS p40,
    APPROX_QUANTILES(diagnostic_load_48hr, 100)[OFFSET(60)] AS p60,
    APPROX_QUANTILES(diagnostic_load_48hr, 100)[OFFSET(80)] AS p80
  FROM
    diagnostic_load
),
stratified_stays AS (
  SELECT
    dl.diagnostic_load_48hr,
    DATETIME_DIFF(dl.outtime, dl.intime, HOUR) / 24.0 AS icu_los_days,
    dl.hospital_expire_flag,
    CASE
      WHEN dl.diagnostic_load_48hr <= b.p20
      THEN 1
      WHEN dl.diagnostic_load_48hr > b.p20 AND dl.diagnostic_load_48hr <= b.p40
      THEN 2
      WHEN dl.diagnostic_load_48hr > b.p40 AND dl.diagnostic_load_48hr <= b.p60
      THEN 3
      WHEN dl.diagnostic_load_48hr > b.p60 AND dl.diagnostic_load_48hr <= b.p80
      THEN 4
      ELSE 5
    END AS diagnostic_load_quintile
  FROM
    diagnostic_load AS dl,
    quintile_boundaries AS b
)
SELECT
  s.diagnostic_load_quintile,
  COUNT(s.diagnostic_load_quintile) AS number_of_stays,
  AVG(s.diagnostic_load_48hr) AS avg_procedure_count,
  AVG(s.icu_los_days) AS avg_icu_los_days,
  AVG(CAST(s.hospital_expire_flag AS FLOAT64)) * 100.0 AS in_hospital_mortality_percent
FROM
  stratified_stays AS s
GROUP BY
  s.diagnostic_load_quintile
ORDER BY
  s.diagnostic_load_quintile;
