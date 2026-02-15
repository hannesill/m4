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
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
  ),
  status_epilepticus AS (
    SELECT DISTINCT di.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` di
    WHERE (di.icd_version = 10 AND di.icd_code LIKE 'G41%')
       OR (di.icd_version = 9 AND di.icd_code LIKE '3453%')
  ),
  target_admissions AS (
    SELECT b.*
    FROM base_admissions b
    JOIN status_epilepticus se USING (hadm_id)
  ),
  meds_24h AS (
    SELECT
      b.hadm_id,
      LOWER(pr.drug) AS drug,
      LOWER(pr.route) AS route,
      pr.starttime,
      COALESCE(pr.stoptime, DATETIME_ADD(pr.starttime, INTERVAL 1 HOUR)) AS stoptime,
      b.admittime
    FROM `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
    JOIN base_admissions b ON pr.hadm_id = b.hadm_id
    WHERE pr.starttime < DATETIME_ADD(b.admittime, INTERVAL 24 HOUR)
      AND COALESCE(pr.stoptime, DATETIME_ADD(pr.starttime, INTERVAL 1 HOUR)) > b.admittime
  ),
  complexity AS (
    SELECT
      hadm_id,
      (
        COUNT(DISTINCT drug) * 2
        + COUNT(DISTINCT route)
        + COUNT(DISTINCT CASE WHEN route LIKE 'iv%' THEN drug END) * 3
      ) AS medication_complexity_score
    FROM meds_24h
    GROUP BY hadm_id
  ),
  ranked AS (
    SELECT
      b.hadm_id,
      b.subject_id,
      b.los_days,
      b.hospital_expire_flag,
      COALESCE(c.medication_complexity_score, 0) AS medication_complexity_score,
      NTILE(100) OVER (ORDER BY COALESCE(c.medication_complexity_score, 0)) AS complexity_percentile,
      NTILE(4) OVER (ORDER BY COALESCE(c.medication_complexity_score, 0)) AS base_complexity_quartile
    FROM base_admissions b
    LEFT JOIN complexity c USING (hadm_id)
  ),
  qt_list AS (
    SELECT 'amiodarone' AS k UNION ALL SELECT 'haloperidol' UNION ALL SELECT 'ziprasidone' UNION ALL
    SELECT 'methadone' UNION ALL SELECT 'citalopram' UNION ALL SELECT 'escitalopram' UNION ALL
    SELECT 'levofloxacin' UNION ALL SELECT 'moxifloxacin' UNION ALL SELECT 'azithromycin' UNION ALL
    SELECT 'ondansetron'
  ),
  anticoag_list AS (
    SELECT 'warfarin' AS k UNION ALL SELECT 'heparin' UNION ALL SELECT 'enoxaparin' UNION ALL
    SELECT 'apixaban' UNION ALL SELECT 'rivaroxaban' UNION ALL SELECT 'dabigatran' UNION ALL
    SELECT 'edoxaban'
  ),
  antiplatelet_list AS (
    SELECT 'aspirin' AS k UNION ALL SELECT 'clopidogrel' UNION ALL SELECT 'prasugrel' UNION ALL
    SELECT 'ticagrelor'
  ),
  antibiotic_list AS (
    SELECT 'ciprofloxacin' AS k UNION ALL SELECT 'levofloxacin' UNION ALL SELECT 'metronidazole' UNION ALL
    SELECT 'trimethoprim' UNION ALL SELECT 'sulfamethoxazole' UNION ALL SELECT 'bactrim' UNION ALL
    SELECT 'clarithromycin' UNION ALL SELECT 'azithromycin' UNION ALL SELECT 'fluconazole'
  ),
  interaction_flags AS (
    SELECT
      b.hadm_id,
      MAX(CASE WHEN qt_pair.hadm_id IS NOT NULL THEN 1 ELSE 0 END) AS has_qt_prolongation_interaction,
      MAX(CASE WHEN bleed_pair.hadm_id IS NOT NULL THEN 1 ELSE 0 END) AS has_bleeding_risk_interaction
    FROM base_admissions b
    LEFT JOIN (
      SELECT DISTINCT m1.hadm_id
      FROM meds_24h m1
      JOIN meds_24h m2
        ON m1.hadm_id = m2.hadm_id AND m1.drug < m2.drug
        AND m1.starttime < m2.stoptime AND m2.starttime < m1.stoptime
      JOIN qt_list q1 ON m1.drug LIKE CONCAT('%', q1.k, '%')
      JOIN qt_list q2 ON m2.drug LIKE CONCAT('%', q2.k, '%')
    ) qt_pair ON b.hadm_id = qt_pair.hadm_id
    LEFT JOIN (
      SELECT DISTINCT m1.hadm_id
      FROM meds_24h m1
      JOIN meds_24h m2
        ON m1.hadm_id = m2.hadm_id AND m1.drug < m2.drug
        AND m1.starttime < m2.stoptime AND m2.starttime < m1.stoptime
      WHERE (
        EXISTS (SELECT 1 FROM anticoag_list ac WHERE m1.drug LIKE CONCAT('%', ac.k, '%')) AND
        EXISTS (SELECT 1 FROM antiplatelet_list ap WHERE m2.drug LIKE CONCAT('%', ap.k, '%'))
      ) OR (
        EXISTS (SELECT 1 FROM anticoag_list ac WHERE m2.drug LIKE CONCAT('%', ac.k, '%')) AND
        EXISTS (SELECT 1 FROM antiplatelet_list ap WHERE m1.drug LIKE CONCAT('%', ap.k, '%'))
      ) OR (
        (m1.drug LIKE '%warfarin%' AND EXISTS (SELECT 1 FROM antibiotic_list ab WHERE m2.drug LIKE CONCAT('%', ab.k, '%')))
        OR (m2.drug LIKE '%warfarin%' AND EXISTS (SELECT 1 FROM antibiotic_list ab WHERE m1.drug LIKE CONCAT('%', ab.k, '%')))
      )
    ) bleed_pair ON b.hadm_id = bleed_pair.hadm_id
    GROUP BY b.hadm_id
  ),
  base_features AS (
    SELECT
      r.hadm_id,
      r.subject_id,
      r.los_days,
      r.hospital_expire_flag,
      r.medication_complexity_score,
      r.complexity_percentile,
      r.base_complexity_quartile,
      COALESCE(f.has_qt_prolongation_interaction, 0) AS has_qt_prolongation_interaction,
      COALESCE(f.has_bleeding_risk_interaction, 0) AS has_bleeding_risk_interaction,
      CASE
        WHEN COALESCE(f.has_qt_prolongation_interaction, 0) = 1 AND COALESCE(f.has_bleeding_risk_interaction, 0) = 1 THEN 'Both'
        WHEN COALESCE(f.has_qt_prolongation_interaction, 0) = 1 THEN 'QT'
        WHEN COALESCE(f.has_bleeding_risk_interaction, 0) = 1 THEN 'Bleeding'
        ELSE 'None'
      END AS interaction_type
    FROM ranked r
    LEFT JOIN interaction_flags f USING (hadm_id)
  ),
  target_ranked AS (
    SELECT
      bf.hadm_id,
      bf.subject_id,
      bf.los_days,
      bf.hospital_expire_flag,
      bf.medication_complexity_score,
      bf.complexity_percentile,
      bf.interaction_type,
      NTILE(4) OVER (ORDER BY bf.medication_complexity_score) AS target_complexity_quartile
    FROM base_features bf
    JOIN target_admissions t USING (hadm_id)
  ),
  general_agg AS (
    SELECT
      'General (Male 39-49)' AS patient_group,
      interaction_type AS interaction_risk_group,
      COUNT(*) AS num_patients,
      ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
      ROUND(AVG(complexity_percentile) / 100.0, 3) AS avg_percentile_rank,
      ROUND(AVG(los_days), 2) AS avg_los_days,
      ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)), 3) AS mortality_rate
    FROM base_features
    GROUP BY interaction_risk_group
  ),
  target_agg AS (
    SELECT
      'Target (Status Epilepticus)' AS patient_group,
      interaction_type AS interaction_risk_group,
      COUNT(*) AS num_patients,
      ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
      ROUND(AVG(complexity_percentile) / 100.0, 3) AS avg_percentile_rank,
      ROUND(AVG(los_days), 2) AS avg_los_days,
      ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)), 3) AS mortality_rate
    FROM target_ranked
    GROUP BY interaction_risk_group
  ),
  target_top_quartile AS (
    SELECT
      'Target (Status Epilepticus)' AS patient_group,
      'Top Quartile' AS interaction_risk_group,
      COUNT(*) AS num_patients,
      ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
      ROUND(AVG(complexity_percentile) / 100.0, 3) AS avg_percentile_rank,
      ROUND(AVG(los_days), 2) AS avg_los_days,
      ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)), 3) AS mortality_rate
    FROM target_ranked
    WHERE target_complexity_quartile = 4
  )
SELECT * FROM general_agg
UNION ALL SELECT * FROM target_agg
UNION ALL SELECT * FROM target_top_quartile
ORDER BY patient_group, interaction_risk_group;
