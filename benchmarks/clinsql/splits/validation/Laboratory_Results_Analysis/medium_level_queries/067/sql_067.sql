WITH
  base_patients AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 52 AND 62
  ),
  ami_admissions AS (
    SELECT DISTINCT
      bp.subject_id,
      bp.hadm_id,
      bp.admittime,
      bp.dischtime,
      bp.hospital_expire_flag,
      bp.age_at_admission
    FROM
      base_patients AS bp
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON bp.hadm_id = d.hadm_id
    WHERE
      d.icd_code LIKE '410%'
      OR d.icd_code LIKE 'I21%'
  ),
  first_troponin_t AS (
    SELECT
      ami.subject_id,
      ami.hadm_id,
      ami.admittime,
      ami.dischtime,
      ami.hospital_expire_flag,
      ami.age_at_admission,
      le.valuenum AS troponin_t_value,
      ROW_NUMBER() OVER (PARTITION BY ami.hadm_id ORDER BY le.charttime ASC) AS rn
    FROM
      ami_admissions AS ami
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      ON ami.hadm_id = le.hadm_id
    WHERE
      le.itemid = 51003
      AND le.valuenum IS NOT NULL
  ),
  final_cohort AS (
    SELECT
      subject_id,
      hadm_id,
      age_at_admission,
      hospital_expire_flag,
      troponin_t_value,
      DATETIME_DIFF(dischtime, admittime, DAY) AS los_days
    FROM
      first_troponin_t
    WHERE
      rn = 1
      AND troponin_t_value > 0.01
      AND dischtime IS NOT NULL
  )
SELECT
  'Female Patients (52-62) with AMI and Elevated First Troponin T' AS cohort_description,
  COUNT(DISTINCT subject_id) AS total_patients,
  COUNT(DISTINCT hadm_id) AS total_admissions,
  ROUND(AVG(age_at_admission), 1) AS avg_age,
  ROUND(AVG(los_days), 1) AS avg_length_of_stay_days,
  ROUND(AVG(troponin_t_value), 3) AS avg_first_troponin_t,
  ROUND(MIN(troponin_t_value), 3) AS min_first_troponin_t,
  ROUND(MAX(troponin_t_value), 3) AS max_first_troponin_t,
  ROUND(STDDEV(troponin_t_value), 3) AS stddev_first_troponin_t,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS in_hospital_mortality_rate_pct
FROM
  final_cohort;
