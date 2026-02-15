WITH
  readmission_30d AS (
    SELECT
      hadm_id,
      CASE
        WHEN LEAD(admittime) OVER (PARTITION BY subject_id ORDER BY admittime) IS NOT NULL
             AND DATETIME_DIFF(
               LEAD(admittime) OVER (PARTITION BY subject_id ORDER BY admittime),
               dischtime,
               DAY
             ) <= 30
        THEN 1 ELSE 0
      END AS is_readmitted_30d
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  base_icu AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      i.stay_id,
      i.intime,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM i.intime) - p.anchor_year) AS age_at_icu,
      ROW_NUMBER() OVER (PARTITION BY a.hadm_id ORDER BY i.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_hosp.patients`   AS p
    JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    JOIN `physionet-data.mimiciv_3_1_icu.icustays`    AS i ON a.hadm_id = i.hadm_id
    WHERE p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM i.intime) - p.anchor_year) BETWEEN 68 AND 78
    QUALIFY rn = 1
  ),
  vaso_stays AS (
    SELECT DISTINCT ie.stay_id
    FROM `physionet-data.mimiciv_3_1_icu.inputevents` AS ie
    JOIN `physionet-data.mimiciv_3_1_icu.icustays`    AS i  ON ie.stay_id = i.stay_id
    WHERE ie.itemid IN (
      221906,
      221289,
      221749,
      222315,
      221662
    )
      AND ie.starttime BETWEEN i.intime AND DATETIME_ADD(i.intime, INTERVAL 72 HOUR)
  ),
  imaging_72h AS (
    SELECT
      c.stay_id,
      COUNT(*) AS imaging_count
    FROM base_icu AS c
    JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe ON c.stay_id = pe.stay_id
    JOIN `physionet-data.mimiciv_3_1_icu.d_items`       AS di ON pe.itemid = di.itemid
    WHERE di.category = 'Imaging'
      AND pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY c.stay_id
  ),
  labs_72h AS (
    SELECT
      c.stay_id,
      COUNT(*) AS lab_count
    FROM base_icu AS c
    JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON c.hadm_id = le.hadm_id
    WHERE le.charttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 72 HOUR)
    GROUP BY c.stay_id
  ),
  diag_load AS (
    SELECT
      c.stay_id,
      c.hadm_id,
      c.hospital_expire_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS hospital_los_days,
      COALESCE(i.imaging_count, 0) + COALESCE(l.lab_count, 0) AS procedure_count,
      COALESCE(r.is_readmitted_30d, 0) AS is_readmitted_30d
    FROM base_icu AS c
    JOIN vaso_stays AS v ON c.stay_id = v.stay_id
    LEFT JOIN imaging_72h AS i ON c.stay_id = i.stay_id
    LEFT JOIN labs_72h   AS l ON c.stay_id = l.stay_id
    LEFT JOIN readmission_30d AS r ON c.hadm_id = r.hadm_id
  ),
  stratified AS (
    SELECT
      *,
      NTILE(4) OVER (ORDER BY procedure_count) AS diagnostic_load_quartile
    FROM diag_load
  )
SELECT
  diagnostic_load_quartile,
  COUNT(*) AS num_patients,
  ROUND(AVG(procedure_count), 2) AS avg_procedure_count,
  ROUND(AVG(hospital_los_days), 2) AS avg_hospital_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(CAST(is_readmitted_30d AS FLOAT64)) * 100, 2) AS readmission_rate_30d_percent
FROM stratified
GROUP BY diagnostic_load_quartile
ORDER BY diagnostic_load_quartile;
