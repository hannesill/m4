WITH
  SurgicalAdmissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.procedures_icd`
    WHERE
      (icd_version = 9 AND SUBSTR(icd_code, 1, 2) BETWEEN '00' AND '86')
      OR (icd_version = 10)
  ),
  PatientCohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) AS age_at_admission,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN SurgicalAdmissions AS sa
      ON a.hadm_id = sa.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 51 AND 61
  ),
  PrescriptionsFirst24h AS (
    SELECT
      pc.hadm_id,
      rx.drug,
      CASE
        WHEN LOWER(rx.drug) LIKE '%norepinephrine%' OR LOWER(rx.drug) LIKE '%epinephrine%' OR LOWER(rx.drug) LIKE '%vasopressin%' OR LOWER(rx.drug) LIKE '%phenylephrine%' OR LOWER(rx.drug) LIKE '%dopamine%' THEN 'Vasoactive'
        WHEN LOWER(rx.drug) LIKE '%amiodarone%' OR LOWER(rx.drug) LIKE '%lidocaine%' THEN 'Antiarrhythmic'
        WHEN LOWER(rx.drug) LIKE '%heparin%' OR LOWER(rx.drug) LIKE '%warfarin%' OR LOWER(rx.drug) LIKE '%enoxaparin%' OR LOWER(rx.drug) LIKE '%argatroban%' OR LOWER(rx.drug) LIKE '%rivaroxaban%' OR LOWER(rx.drug) LIKE '%apixaban%' THEN 'Anticoagulant'
        WHEN LOWER(rx.drug) LIKE '%propofol%' OR LOWER(rx.drug) LIKE '%midazolam%' OR LOWER(rx.drug) LIKE '%dexmedetomidine%' OR LOWER(rx.drug) LIKE '%lorazepam%' THEN 'Sedative/Anesthetic'
        WHEN LOWER(rx.drug) LIKE '%vancomycin%' OR LOWER(rx.drug) LIKE '%meropenem%' OR LOWER(rx.drug) LIKE '%piperacillin%' OR LOWER(rx.drug) LIKE '%tazobactam%' THEN 'Broad-Spectrum Antibiotic'
        ELSE NULL
      END AS high_risk_class
    FROM PatientCohort AS pc
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON pc.hadm_id = rx.hadm_id
    WHERE
      rx.starttime BETWEEN pc.admittime AND DATETIME_ADD(pc.admittime, INTERVAL 24 HOUR)
  ),
  MedComplexity AS (
    SELECT
      hadm_id,
      (COUNT(DISTINCT drug) + (COUNT(DISTINCT high_risk_class) * 2)) AS med_complexity_score
    FROM PrescriptionsFirst24h
    GROUP BY hadm_id
  ),
  ReadmissionFlag AS (
    SELECT
      hadm_id,
      CASE
        WHEN LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) < DATETIME_ADD(dischtime, INTERVAL 30 DAY)
        THEN 1
        ELSE 0
      END AS readmitted_30_day_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions`
    WHERE subject_id IN (SELECT DISTINCT subject_id FROM PatientCohort)
  ),
  PatientOutcomes AS (
    SELECT
      pc.hadm_id,
      COALESCE(mc.med_complexity_score, 0) AS med_complexity_score,
      pc.los_days,
      pc.hospital_expire_flag,
      COALESCE(rf.readmitted_30_day_flag, 0) AS readmitted_30_day_flag,
      NTILE(4) OVER (ORDER BY COALESCE(mc.med_complexity_score, 0)) AS complexity_quartile
    FROM PatientCohort AS pc
    LEFT JOIN MedComplexity AS mc
      ON pc.hadm_id = mc.hadm_id
    LEFT JOIN ReadmissionFlag AS rf
      ON pc.hadm_id = rf.hadm_id
  )
SELECT
  complexity_quartile,
  COUNT(hadm_id) AS num_patients,
  MIN(med_complexity_score) AS min_complexity_score,
  MAX(med_complexity_score) AS max_complexity_score,
  ROUND(AVG(med_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(readmitted_30_day_flag) * 100, 2) AS readmission_rate_30_day_pct
FROM PatientOutcomes
GROUP BY complexity_quartile
ORDER BY complexity_quartile;
