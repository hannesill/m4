WITH
  BaseAdmissions AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      pat.gender,
      (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age AS age_at_admission,
      adm.admittime,
      adm.dischtime,
      TIMESTAMP_DIFF(adm.dischtime, adm.admittime, DAY) AS los,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    WHERE
      pat.gender = 'F'
      AND (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age BETWEEN 48 AND 58
  ),
  HemorrhagicStrokeCohort AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND (
        icd_code LIKE '430%'
        OR icd_code LIKE '431%'
        OR icd_code LIKE '432%'
      ))
      OR (icd_version = 10 AND (
        icd_code LIKE 'I60%'
        OR icd_code LIKE 'I61%'
        OR icd_code LIKE 'I62%'
      ))
  ),
  MedicationsFirst48h AS (
    SELECT
      pres.hadm_id,
      pres.drug,
      CASE
        WHEN LOWER(pres.drug) LIKE '%sertraline%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%fluoxetine%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%citalopram%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%escitalopram%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%paroxetine%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%venlafaxine%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%duloxetine%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%amitriptyline%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%nortriptyline%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%trazodone%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%tramadol%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%fentanyl%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%meperidine%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%methadone%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%ondansetron%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%sumatriptan%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%linezolid%' THEN 1
        WHEN LOWER(pres.drug) LIKE '%methylene blue%' THEN 1
        ELSE 0
      END AS is_serotonergic
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pres
    JOIN
      BaseAdmissions AS adm
      ON pres.hadm_id = adm.hadm_id
    WHERE
      pres.starttime <= TIMESTAMP_ADD(adm.admittime, INTERVAL 48 HOUR)
  ),
  PatientLevelStats AS (
    SELECT
      b.hadm_id,
      b.los,
      b.hospital_expire_flag,
      CASE
        WHEN hsc.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS is_hemorrhagic_stroke_patient,
      COUNT(DISTINCT meds.drug) AS medication_complexity_score,
      CASE
        WHEN COUNT(DISTINCT CASE WHEN meds.is_serotonergic = 1 THEN meds.drug END) >= 2 THEN 1
        ELSE 0
      END AS has_serotonergic_interaction_risk
    FROM
      BaseAdmissions AS b
    LEFT JOIN
      HemorrhagicStrokeCohort AS hsc
      ON b.hadm_id = hsc.hadm_id
    LEFT JOIN
      MedicationsFirst48h AS meds
      ON b.hadm_id = meds.hadm_id
    GROUP BY
      b.hadm_id,
      b.los,
      b.hospital_expire_flag,
      is_hemorrhagic_stroke_patient
  ),
  PatientLevelRanks AS (
    SELECT
      *,
      PERCENT_RANK() OVER (
        PARTITION BY is_hemorrhagic_stroke_patient
        ORDER BY medication_complexity_score
      ) AS complexity_percentile_rank,
      NTILE(4) OVER (
        PARTITION BY is_hemorrhagic_stroke_patient
        ORDER BY medication_complexity_score DESC
      ) AS complexity_quartile
    FROM
      PatientLevelStats
  )
SELECT
  CASE
    WHEN is_hemorrhagic_stroke_patient = 1 THEN 'Hemorrhagic Stroke (48-58 F)'
    ELSE 'Age-Matched Control (48-58 F)'
  END AS cohort,
  'All Patients' AS subgroup,
  COUNT(hadm_id) AS patient_count,
  ROUND(AVG(medication_complexity_score), 2) AS avg_medication_complexity,
  ROUND(AVG(los), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag), 4) AS mortality_rate
FROM
  PatientLevelRanks
GROUP BY
  cohort,
  is_hemorrhagic_stroke_patient
UNION ALL
SELECT
  CASE
    WHEN is_hemorrhagic_stroke_patient = 1 THEN 'Hemorrhagic Stroke (48-58 F)'
    ELSE 'Age-Matched Control (48-58 F)'
  END AS cohort,
  CASE
    WHEN has_serotonergic_interaction_risk = 1 THEN 'Interaction Risk (>=2 Sero. Drugs)'
    ELSE 'No/Low Interaction Risk (<2 Sero. Drugs)'
  END AS subgroup,
  COUNT(hadm_id) AS patient_count,
  ROUND(AVG(medication_complexity_score), 2) AS avg_medication_complexity,
  ROUND(AVG(los), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag), 4) AS mortality_rate
FROM
  PatientLevelRanks
GROUP BY
  cohort,
  subgroup,
  is_hemorrhagic_stroke_patient
UNION ALL
SELECT
  'Hemorrhagic Stroke (48-58 F)' AS cohort,
  'Top 25% Complexity (Quartile 1)' AS subgroup,
  COUNT(hadm_id) AS patient_count,
  ROUND(AVG(medication_complexity_score), 2) AS avg_medication_complexity,
  ROUND(AVG(los), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag), 4) AS mortality_rate
FROM
  PatientLevelRanks
WHERE
  is_hemorrhagic_stroke_patient = 1
  AND complexity_quartile = 1
GROUP BY
  cohort,
  subgroup
ORDER BY
  cohort,
  subgroup;
