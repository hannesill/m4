WITH
admission_sequences AS (
  SELECT
    subject_id,
    hadm_id,
    admittime,
    dischtime,
    LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions`
),
hemorrhagic_stroke_cohort AS (
  SELECT DISTINCT
    a.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    a.hospital_expire_flag,
    CASE
      WHEN DATETIME_DIFF(seq.next_admittime, a.dischtime, DAY) <= 30 THEN 1
      ELSE 0
    END AS readmitted_30_days,
    DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
  FROM
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON a.subject_id = p.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
  LEFT JOIN
    admission_sequences AS seq
    ON a.hadm_id = seq.hadm_id
  WHERE
    p.gender = 'M'
    AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age) BETWEEN 61 AND 71
    AND (
      (d.icd_version = 9 AND (d.icd_code LIKE '430%' OR d.icd_code LIKE '431%' OR d.icd_code LIKE '432%'))
      OR
      (d.icd_version = 10 AND (d.icd_code LIKE 'I60%' OR d.icd_code LIKE 'I61%' OR d.icd_code LIKE 'I62%'))
    )
),
first_24h_meds AS (
  SELECT
    cohort.hadm_id,
    rx.drug,
    rx.route,
    CASE
      WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
      WHEN LOWER(rx.drug) LIKE '%heparin%' OR LOWER(rx.drug) LIKE '%enoxaparin%' OR LOWER(rx.drug) LIKE '%warfarin%' OR LOWER(rx.drug) LIKE '%fondaparinux%' THEN 'Anticoagulant'
      WHEN LOWER(rx.drug) LIKE '%norepinephrine%' OR LOWER(rx.drug) LIKE '%epinephrine%' OR LOWER(rx.drug) LIKE '%vasopressin%' OR LOWER(rx.drug) LIKE '%dopamine%' OR LOWER(rx.drug) LIKE '%phenylephrine%' THEN 'Vasopressor'
      WHEN LOWER(rx.drug) LIKE '%amiodarone%' OR LOWER(rx.drug) LIKE '%lidocaine%' THEN 'Antiarrhythmic'
      WHEN LOWER(rx.drug) LIKE '%propofol%' OR LOWER(rx.drug) LIKE '%midazolam%' OR LOWER(rx.drug) LIKE '%dexmedetomidine%' THEN 'Sedative'
      ELSE NULL
    END AS high_risk_class
  FROM
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
  INNER JOIN
    hemorrhagic_stroke_cohort AS cohort
    ON rx.hadm_id = cohort.hadm_id
  WHERE
    rx.starttime BETWEEN cohort.admittime AND DATETIME_ADD(cohort.admittime, INTERVAL 24 HOUR)
),
admission_complexity AS (
  SELECT
    hadm_id,
    (COUNT(DISTINCT drug) * 1) + (COUNT(DISTINCT route) * 2) + (COUNT(DISTINCT high_risk_class) * 3) AS medication_complexity_score
  FROM
    first_24h_meds
  GROUP BY
    hadm_id
),
stratified_outcomes AS (
  SELECT
    cohort.hadm_id,
    cohort.los_days,
    cohort.hospital_expire_flag,
    cohort.readmitted_30_days,
    COALESCE(comp.medication_complexity_score, 0) AS medication_complexity_score,
    NTILE(5) OVER (ORDER BY COALESCE(comp.medication_complexity_score, 0)) AS complexity_quintile
  FROM
    hemorrhagic_stroke_cohort AS cohort
  LEFT JOIN
    admission_complexity AS comp
    ON cohort.hadm_id = comp.hadm_id
)
SELECT
  complexity_quintile,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(AVG(medication_complexity_score), 2) AS avg_medication_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_length_of_stay_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS in_hospital_mortality_rate_percent,
  ROUND(AVG(readmitted_30_days) * 100, 2) AS readmission_rate_30_day_percent
FROM
  stratified_outcomes
GROUP BY
  complexity_quintile
ORDER BY
  complexity_quintile;
