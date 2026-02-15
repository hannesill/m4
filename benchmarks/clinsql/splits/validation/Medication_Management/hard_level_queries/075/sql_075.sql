WITH
  cohort_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (
        EXTRACT(YEAR FROM a.admittime) - p.anchor_year
      ) + p.anchor_age AS age_at_admission,
      TIMESTAMP_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND d.icd_code IN ('49121', 'J441')
      AND (
        (
          EXTRACT(YEAR FROM a.admittime) - p.anchor_year
        ) + p.anchor_age
      ) BETWEEN 58 AND 68
  ),
  readmission_info AS (
    SELECT
      hadm_id,
      CASE
        WHEN TIMESTAMP_DIFF(next_admittime, dischtime, DAY) <= 30 THEN 1
        ELSE 0
      END AS readmitted_30_day
    FROM
      (
        SELECT
          subject_id,
          hadm_id,
          admittime,
          dischtime,
          LEAD(admittime, 1) OVER (
            PARTITION BY
              subject_id
            ORDER BY
              admittime
          ) AS next_admittime
        FROM
          `physionet-data.mimiciv_3_1_hosp.admissions`
      ) AS next_adm
    WHERE
      hadm_id IN (
        SELECT
          hadm_id
        FROM
          cohort_admissions
      )
  ),
  medication_complexity AS (
    SELECT
      pres.hadm_id,
      (COUNT(DISTINCT pres.drug) * 3) + (COUNT(DISTINCT pres.route) * 2) + COUNT(*) AS medication_complexity_score,
      MAX(
        CASE
          WHEN flag_anticoagulant = 1 AND flag_nsaid = 1 THEN 1
          ELSE 0
        END
      ) AS has_anticoag_nsaid_interaction
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pres
      INNER JOIN cohort_admissions AS cohort ON pres.hadm_id = cohort.hadm_id
      CROSS JOIN UNNEST(
        [
          STRUCT(
            CASE
              WHEN LOWER(pres.drug) LIKE '%warfarin%'
              OR LOWER(pres.drug) LIKE '%heparin%'
              OR LOWER(pres.drug) LIKE '%enoxaparin%'
              OR LOWER(pres.drug) LIKE '%apixaban%'
              OR LOWER(pres.drug) LIKE '%rivaroxaban%' THEN 1
              ELSE 0
            END AS flag_anticoagulant,
            CASE
              WHEN LOWER(pres.drug) LIKE '%ibuprofen%'
              OR LOWER(pres.drug) LIKE '%naproxen%'
              OR LOWER(pres.drug) LIKE '%ketorolac%'
              OR LOWER(pres.drug) LIKE '%diclofenac%' THEN 1
              ELSE 0
            END AS flag_nsaid
          )
        ]
      ) AS flags
    WHERE
      pres.starttime <= TIMESTAMP_ADD(cohort.admittime, INTERVAL 72 HOUR)
    GROUP BY
      pres.hadm_id
  ),
  stratified_cohort AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      c.los_days,
      r.readmitted_30_day,
      mc.medication_complexity_score,
      mc.has_anticoag_nsaid_interaction,
      NTILE(3) OVER (
        ORDER BY
          mc.medication_complexity_score
      ) AS complexity_tertile
    FROM
      cohort_admissions AS c
      INNER JOIN medication_complexity AS mc ON c.hadm_id = mc.hadm_id
      LEFT JOIN readmission_info AS r ON c.hadm_id = r.hadm_id
  )
SELECT
  complexity_tertile,
  COUNT(DISTINCT hadm_id) AS number_of_patients,
  MIN(medication_complexity_score) AS min_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(medication_complexity_score), 1) AS avg_complexity_score,
  ROUND(AVG(los_days), 1) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(COALESCE(readmitted_30_day, 0)) * 100, 2) AS readmission_rate_30day_pct,
  ROUND(
    AVG(has_anticoag_nsaid_interaction) * 100,
    2
  ) AS pct_with_high_risk_interaction
FROM
  stratified_cohort
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
