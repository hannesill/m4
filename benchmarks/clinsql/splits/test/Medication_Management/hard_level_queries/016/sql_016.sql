WITH
  cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (
        EXTRACT(YEAR FROM a.admittime) - p.anchor_year
      ) + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (
        (
          EXTRACT(YEAR FROM a.admittime) - p.anchor_year
        ) + p.anchor_age
      ) BETWEEN 80 AND 90
      AND a.hadm_id IN (
        SELECT
          dx.hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE
          (
            dx.icd_version = 9
            AND (
              dx.icd_code LIKE '571%'
              OR dx.icd_code LIKE '572%'
              OR dx.icd_code LIKE '573%'
            )
          )
          OR (
            dx.icd_version = 10
            AND (
              dx.icd_code LIKE 'K70%'
              OR dx.icd_code LIKE 'K71%'
              OR dx.icd_code LIKE 'K72%'
              OR dx.icd_code LIKE 'K73%'
              OR dx.icd_code LIKE 'K74%'
              OR dx.icd_code LIKE 'K75%'
              OR dx.icd_code LIKE 'K76%'
            )
          )
      )
  ),
  meds_first_7_days AS (
    SELECT
      c.hadm_id,
      pr.drug,
      pr.route
    FROM
      cohort AS c
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr ON c.hadm_id = pr.hadm_id
    WHERE
      pr.starttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 7 DAY)
  ),
  complexity_scores AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT drug) AS unique_med_count,
      COUNT(DISTINCT route) AS unique_route_count,
      COUNT(
        DISTINCT CASE
          WHEN LOWER(drug) LIKE '%heparin%'
          OR LOWER(drug) LIKE '%warfarin%'
          OR LOWER(drug) LIKE '%enoxaparin%'
          OR LOWER(drug) LIKE '%rivaroxaban%'
          OR LOWER(drug) LIKE '%apixaban%' THEN 'anticoagulant'
          WHEN LOWER(drug) LIKE '%insulin%' THEN 'insulin'
          WHEN LOWER(drug) LIKE '%morphine%'
          OR LOWER(drug) LIKE '%fentanyl%'
          OR LOWER(drug) LIKE '%hydromorphone%'
          OR LOWER(drug) LIKE '%oxycodone%' THEN 'opioid'
          ELSE NULL
        END
      ) AS high_risk_class_count,
      (
        (COUNT(DISTINCT drug) * 1) + (COUNT(DISTINCT route) * 2) + (
          COUNT(
            DISTINCT CASE
              WHEN LOWER(drug) LIKE '%heparin%'
              OR LOWER(drug) LIKE '%warfarin%'
              OR LOWER(drug) LIKE '%enoxaparin%'
              OR LOWER(drug) LIKE '%rivaroxaban%'
              OR LOWER(drug) LIKE '%apixaban%' THEN 'anticoagulant'
              WHEN LOWER(drug) LIKE '%insulin%' THEN 'insulin'
              WHEN LOWER(drug) LIKE '%morphine%'
              OR LOWER(drug) LIKE '%fentanyl%'
              OR LOWER(drug) LIKE '%hydromorphone%'
              OR LOWER(drug) LIKE '%oxycodone%' THEN 'opioid'
              ELSE NULL
            END
          ) * 3
        )
      ) AS medication_complexity_score
    FROM
      meds_first_7_days
    GROUP BY
      hadm_id
  ),
  admission_sequences AS (
    SELECT
      hadm_id,
      dischtime,
      LEAD(admittime, 1) OVER (
        PARTITION BY
          subject_id
        ORDER BY
          admittime
      ) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  patient_outcomes AS (
    SELECT
      c.hadm_id,
      c.subject_id,
      cs.medication_complexity_score,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
      c.hospital_expire_flag,
      CASE
        WHEN DATETIME_DIFF(seq.next_admittime, c.dischtime, DAY) <= 30 THEN 1
        ELSE 0
      END AS readmitted_30_days
    FROM
      cohort AS c
      LEFT JOIN complexity_scores AS cs ON c.hadm_id = cs.hadm_id
      LEFT JOIN admission_sequences AS seq ON c.hadm_id = seq.hadm_id
  ),
  ranked_patients AS (
    SELECT
      hadm_id,
      subject_id,
      COALESCE(medication_complexity_score, 0) AS medication_complexity_score,
      los_days,
      hospital_expire_flag,
      readmitted_30_days,
      NTILE(3) OVER (
        ORDER BY
          COALESCE(medication_complexity_score, 0)
      ) AS complexity_tertile,
      PERCENT_RANK() OVER (
        ORDER BY
          COALESCE(medication_complexity_score, 0)
      ) AS complexity_percentile_rank
    FROM
      patient_outcomes
  )
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS num_admissions,
  MIN(medication_complexity_score) AS min_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(readmitted_30_days) * 100, 2) AS readmission_rate_30_day_pct
FROM
  ranked_patients
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
