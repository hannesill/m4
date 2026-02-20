WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      p.gender,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_hosp.admissions` a
      ON p.subject_id = a.subject_id
    WHERE p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 43 AND 53
  ),
  hepatic_failure AS (
    SELECT DISTINCT di.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` di
    WHERE (di.icd_version = 10 AND di.icd_code LIKE 'K72%')
       OR (di.icd_version = 9 AND (di.icd_code = '570' OR di.icd_code = '5722'))
  ),
  target_admissions AS (
    SELECT b.*
    FROM base_admissions b
    JOIN hepatic_failure h USING (hadm_id)
  ),
  meds_72h AS (
    SELECT
      t.hadm_id,
      LOWER(pr.drug) AS drug,
      LOWER(pr.route) AS route,
      pr.starttime,
      COALESCE(pr.stoptime, DATETIME_ADD(pr.starttime, INTERVAL 1 HOUR)) AS stoptime,
      t.admittime
    FROM `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
    JOIN target_admissions t ON pr.hadm_id = t.hadm_id
    WHERE pr.starttime < DATETIME_ADD(t.admittime, INTERVAL 72 HOUR)
      AND COALESCE(pr.stoptime, DATETIME_ADD(pr.starttime, INTERVAL 1 HOUR)) > t.admittime
  ),
  complexity AS (
    SELECT
      hadm_id,
      (
        COUNT(DISTINCT drug) * 2
        + COUNT(DISTINCT route)
        + COUNT(DISTINCT CASE WHEN route LIKE 'iv%' THEN drug END) * 3
      ) AS medication_complexity_score
    FROM meds_72h
    GROUP BY hadm_id
  ),
  readmission_flags AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(
          LEAD(admittime) OVER (PARTITION BY subject_id ORDER BY admittime),
          dischtime,
          DAY
        ) <= 30 THEN 1 ELSE 0 END AS readmitted_30d
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  target_with_scores AS (
    SELECT
      t.hadm_id,
      t.subject_id,
      t.los_days,
      t.hospital_expire_flag,
      COALESCE(c.medication_complexity_score, 0) AS medication_complexity_score,
      NTILE(5) OVER (ORDER BY COALESCE(c.medication_complexity_score, 0)) AS complexity_quintile,
      COALESCE(r.readmitted_30d, 0) AS readmitted_30d
    FROM target_admissions t
    LEFT JOIN complexity c USING (hadm_id)
    LEFT JOIN readmission_flags r USING (hadm_id)
  )
SELECT
  complexity_quintile,
  COUNT(*) AS num_patients_in_stratum,
  MIN(medication_complexity_score) AS min_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(CAST(readmitted_30d AS FLOAT64)) * 100, 2) AS readmission_rate_30d_pct
FROM target_with_scores
GROUP BY complexity_quintile
ORDER BY complexity_quintile;
