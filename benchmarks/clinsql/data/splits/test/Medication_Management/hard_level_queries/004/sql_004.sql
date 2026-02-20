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
    WHERE p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 48 AND 58
  ),
  ischemic_stroke AS (
    SELECT DISTINCT di.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` di
    WHERE (di.icd_version = 10 AND di.icd_code LIKE 'I63%')
       OR (di.icd_version = 9 AND (di.icd_code LIKE '433%1' OR di.icd_code LIKE '434%1'))
  ),
  target_admissions AS (
    SELECT b.*
    FROM base_admissions b
    JOIN ischemic_stroke s USING (hadm_id)
  ),
  meds_hosp AS (
    SELECT
      b.hadm_id,
      LOWER(pr.drug) AS drug,
      LOWER(pr.route) AS route,
      pr.starttime,
      COALESCE(pr.stoptime, DATETIME_ADD(pr.starttime, INTERVAL 1 HOUR)) AS stoptime,
      b.admittime,
      b.dischtime
    FROM `physionet-data.mimiciv_3_1_hosp.prescriptions` pr
    JOIN base_admissions b ON pr.hadm_id = b.hadm_id
    WHERE pr.starttime < b.dischtime
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
    FROM meds_hosp
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
  nti_list AS (
    SELECT 'warfarin' AS k UNION ALL SELECT 'digoxin' UNION ALL SELECT 'tacrolimus' UNION ALL
    SELECT 'cyclosporine' UNION ALL SELECT 'sirolimus' UNION ALL SELECT 'theophylline'
  ),
  cyp3a4_inhibitors AS (
    SELECT 'clarithromycin' AS k UNION ALL SELECT 'erythromycin' UNION ALL SELECT 'ketoconazole' UNION ALL
    SELECT 'itraconazole' UNION ALL SELECT 'voriconazole' UNION ALL SELECT 'fluconazole' UNION ALL
    SELECT 'diltiazem' UNION ALL SELECT 'verapamil' UNION ALL SELECT 'amiodarone' UNION ALL
    SELECT 'cobicistat'
  ),
  cyp3a4_inducers AS (
    SELECT 'rifampin' AS k UNION ALL SELECT 'carbamazepine' UNION ALL SELECT 'phenytoin' UNION ALL
    SELECT 'phenobarbital'
  ),
  interaction_flags AS (
    SELECT
      b.hadm_id,
      MAX(CASE WHEN inh_pair.hadm_id IS NOT NULL THEN 1 ELSE 0 END) AS has_cyp3a4_nti_inhibitor_interaction,
      MAX(CASE WHEN ind_pair.hadm_id IS NOT NULL THEN 1 ELSE 0 END) AS has_cyp3a4_nti_inducer_interaction
    FROM base_admissions b
    LEFT JOIN (
      SELECT DISTINCT m1.hadm_id
      FROM meds_hosp m1
      JOIN meds_hosp m2
        ON m1.hadm_id = m2.hadm_id AND m1.drug < m2.drug
        AND m1.starttime < m2.stoptime AND m2.starttime < m1.stoptime
      WHERE (
        EXISTS (SELECT 1 FROM cyp3a4_inhibitors i WHERE m1.drug LIKE CONCAT('%', i.k, '%')) AND
        EXISTS (SELECT 1 FROM nti_list n WHERE m2.drug LIKE CONCAT('%', n.k, '%'))
      ) OR (
        EXISTS (SELECT 1 FROM cyp3a4_inhibitors i WHERE m2.drug LIKE CONCAT('%', i.k, '%')) AND
        EXISTS (SELECT 1 FROM nti_list n WHERE m1.drug LIKE CONCAT('%', n.k, '%'))
      )
    ) inh_pair ON b.hadm_id = inh_pair.hadm_id
    LEFT JOIN (
      SELECT DISTINCT m1.hadm_id
      FROM meds_hosp m1
      JOIN meds_hosp m2
        ON m1.hadm_id = m2.hadm_id AND m1.drug < m2.drug
        AND m1.starttime < m2.stoptime AND m2.starttime < m1.stoptime
      WHERE (
        EXISTS (SELECT 1 FROM cyp3a4_inducers i WHERE m1.drug LIKE CONCAT('%', i.k, '%')) AND
        EXISTS (SELECT 1 FROM nti_list n WHERE m2.drug LIKE CONCAT('%', n.k, '%'))
      ) OR (
        EXISTS (SELECT 1 FROM cyp3a4_inducers i WHERE m2.drug LIKE CONCAT('%', i.k, '%')) AND
        EXISTS (SELECT 1 FROM nti_list n WHERE m1.drug LIKE CONCAT('%', n.k, '%'))
      )
    ) ind_pair ON b.hadm_id = ind_pair.hadm_id
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
      COALESCE(f.has_cyp3a4_nti_inhibitor_interaction, 0) AS has_cyp3a4_nti_inhibitor_interaction,
      COALESCE(f.has_cyp3a4_nti_inducer_interaction, 0) AS has_cyp3a4_nti_inducer_interaction
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
      NTILE(4) OVER (ORDER BY bf.medication_complexity_score) AS target_complexity_quartile,
      (bf.has_cyp3a4_nti_inhibitor_interaction = 1 OR bf.has_cyp3a4_nti_inducer_interaction = 1) AS has_interaction
    FROM base_features bf
    JOIN target_admissions t USING (hadm_id)
  ),
  general_agg AS (
    SELECT
      'General (Female 48-58)' AS patient_group,
      CAST((has_cyp3a4_nti_inhibitor_interaction = 1 OR has_cyp3a4_nti_inducer_interaction = 1) AS STRING) AS interaction_risk_group,
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
      'Target (Ischemic Stroke)' AS patient_group,
      CAST(has_interaction AS STRING) AS interaction_risk_group,
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
      'Target (Ischemic Stroke)' AS patient_group,
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
