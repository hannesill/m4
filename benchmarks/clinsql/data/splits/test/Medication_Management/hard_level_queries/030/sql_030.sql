WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (
        (EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age
      ) BETWEEN 71 AND 81
      AND (
        (d.icd_version = 9 AND d.icd_code = '5770')
        OR (d.icd_version = 10 AND STARTS_WITH(d.icd_code, 'K85'))
      )
    GROUP BY
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
  ),
  readmission_info AS (
    SELECT
      hadm_id,
      CASE
        WHEN
          DATETIME_DIFF(
            LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime),
            dischtime,
            DAY
          ) <= 30
          THEN 1
        ELSE 0
      END AS readmitted_30_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  meds_in_window AS (
    SELECT
      c.hadm_id,
      pr.drug,
      pr.route,
      CASE
        WHEN LOWER(pr.drug) LIKE '%insulin%'
        THEN 'Insulin'
        WHEN LOWER(pr.drug) LIKE '%warfarin%' OR LOWER(pr.drug) LIKE '%coumadin%'
        THEN 'Warfarin'
        WHEN LOWER(pr.drug) LIKE '%heparin%'
        THEN 'Heparin'
        WHEN
          LOWER(pr.drug) LIKE '%morphine%'
          OR LOWER(pr.drug) LIKE '%fentanyl%'
          OR LOWER(pr.drug) LIKE '%oxycodone%'
          OR LOWER(pr.drug) LIKE '%hydromorphone%'
        THEN 'Opioid'
        WHEN LOWER(pr.drug) LIKE '%digoxin%'
        THEN 'Digoxin'
        ELSE NULL
      END AS high_risk_class
    FROM
      patient_cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON c.hadm_id = pr.hadm_id
    WHERE
      pr.starttime >= c.admittime AND pr.starttime <= DATETIME_ADD(c.admittime, INTERVAL 72 HOUR)
  ),
  complexity_scores AS (
    SELECT
      hadm_id,
      (
        (COUNT(DISTINCT drug) * 1.0)
        + (COUNT(DISTINCT route) * 1.5)
        + (COUNT(DISTINCT high_risk_class) * 2.0)
      ) AS medication_complexity_score
    FROM
      meds_in_window
    GROUP BY
      hadm_id
  ),
  patient_outcomes AS (
    SELECT
      c.hadm_id,
      c.admittime,
      c.dischtime,
      c.hospital_expire_flag,
      COALESCE(cs.medication_complexity_score, 0) AS medication_complexity_score,
      COALESCE(ri.readmitted_30_days, 0) AS readmitted_30_days,
      NTILE(3) OVER (ORDER BY COALESCE(cs.medication_complexity_score, 0)) AS complexity_tertile
    FROM
      patient_cohort AS c
    LEFT JOIN
      complexity_scores AS cs
      ON c.hadm_id = cs.hadm_id
    LEFT JOIN
      readmission_info AS ri
      ON c.hadm_id = ri.hadm_id
  )
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS num_patients,
  MIN(medication_complexity_score) AS min_complexity_score,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(DATETIME_DIFF(dischtime, admittime, HOUR)) / 24.0, 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(CAST(readmitted_30_days AS FLOAT64)) * 100, 2) AS readmission_rate_30day_pct
FROM
  patient_outcomes
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
