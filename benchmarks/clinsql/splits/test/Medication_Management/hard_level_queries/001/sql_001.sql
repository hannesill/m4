WITH
  cohort_base AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
  ),
  cardiac_arrest_cohort AS (
    SELECT
      cb.subject_id,
      cb.hadm_id,
      cb.admittime,
      cb.dischtime,
      cb.hospital_expire_flag
    FROM
      cohort_base AS cb
    WHERE
      cb.age_at_admission BETWEEN 76 AND 86
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE d.hadm_id = cb.hadm_id
          AND (
            (d.icd_version = 9 AND d.icd_code = '4275')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I46%')
          )
      )
  ),
  readmissions AS (
    SELECT
      a.hadm_id,
      CASE
        WHEN DATETIME_DIFF(LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime), a.dischtime, DAY) <= 30
        THEN 1
        ELSE 0
      END AS readmitted_30_days_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` a
    WHERE a.subject_id IN (SELECT DISTINCT subject_id FROM cardiac_arrest_cohort)
  ),
  meds_first_7_days AS (
    SELECT
      c.hadm_id,
      pr.drug,
      pr.route
    FROM
      cardiac_arrest_cohort AS c
    JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON c.hadm_id = pr.hadm_id
    WHERE
      pr.starttime <= DATETIME_ADD(c.admittime, INTERVAL 7 DAY)
  ),
  complexity_features AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT drug) AS unique_drug_count,
      COUNT(DISTINCT route) AS unique_route_count,
      COUNT(*) AS total_prescriptions,
      (
        CAST(COUNTIF(LOWER(drug) LIKE '%norepinephrine%' OR LOWER(drug) LIKE '%epinephrine%' OR LOWER(drug) LIKE '%dopamine%' OR LOWER(drug) LIKE '%vasopressin%' OR LOWER(drug) LIKE '%dobutamine%' OR LOWER(drug) LIKE '%phenylephrine%') > 0 AS INT64) +
        CAST(COUNTIF(LOWER(drug) LIKE '%amiodarone%' OR LOWER(drug) LIKE '%lidocaine%' OR LOWER(drug) LIKE '%procainamide%') > 0 AS INT64) +
        CAST(COUNTIF(LOWER(drug) LIKE '%heparin%' OR LOWER(drug) LIKE '%warfarin%' OR LOWER(drug) LIKE '%enoxaparin%' OR LOWER(drug) LIKE '%argatroban%' OR LOWER(drug) LIKE '%bivalirudin%') > 0 AS INT64)
      ) AS high_risk_med_class_count
    FROM
      meds_first_7_days
    GROUP BY
      hadm_id
  ),
  cohort_with_scores AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
      COALESCE(r.readmitted_30_days_flag, 0) AS readmitted_30_days_flag,
      (
        (cf.unique_drug_count * 1.5) +
        (cf.unique_route_count * 1.0) +
        (cf.total_prescriptions * 0.2) +
        (cf.high_risk_med_class_count * 5.0)
      ) AS med_complexity_score
    FROM
      cardiac_arrest_cohort AS c
    LEFT JOIN
      complexity_features AS cf
      ON c.hadm_id = cf.hadm_id
    LEFT JOIN
      readmissions AS r
      ON c.hadm_id = r.hadm_id
  ),
  ranked_cohort AS (
    SELECT
      *,
      NTILE(5) OVER (ORDER BY med_complexity_score) AS complexity_quintile
    FROM
      cohort_with_scores
    WHERE med_complexity_score IS NOT NULL
  )
SELECT
  complexity_quintile,
  COUNT(*) AS num_patients,
  ROUND(AVG(med_complexity_score), 2) AS avg_complexity_score,
  ROUND(MIN(med_complexity_score), 2) AS min_score_in_quintile,
  ROUND(MAX(med_complexity_score), 2) AS max_score_in_quintile,
  ROUND(AVG(los_days), 1) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(readmitted_30_days_flag) * 100, 2) AS readmission_rate_30_day_percent
FROM
  ranked_cohort
GROUP BY
  complexity_quintile
ORDER BY
  complexity_quintile;
