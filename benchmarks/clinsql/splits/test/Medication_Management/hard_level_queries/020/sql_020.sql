WITH
  cohort_admissions AS (
    SELECT DISTINCT
      p.subject_id,
      ad.hadm_id,
      ad.admittime,
      ad.dischtime,
      ad.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS ad
      ON p.subject_id = ad.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON ad.hadm_id = dx.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM ad.admittime) - p.anchor_year) BETWEEN 78 AND 88
      AND (dx.icd_code = '4275' OR dx.icd_code LIKE 'I46%')
  ),
  meds_first_7_days AS (
    SELECT
      c.hadm_id,
      pr.drug,
      pr.route
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
    INNER JOIN
      cohort_admissions AS c
      ON pr.hadm_id = c.hadm_id
    WHERE
      pr.starttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 7 DAY)
  ),
  complexity_features AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT drug) AS unique_drug_count,
      COUNT(DISTINCT route) AS unique_route_count,
      COUNT(
        DISTINCT CASE
          WHEN
            LOWER(drug) LIKE '%norepinephrine%' OR LOWER(drug) LIKE '%epinephrine%'
            OR LOWER(drug) LIKE '%vasopressin%' OR LOWER(drug) LIKE '%dopamine%'
            OR LOWER(drug) LIKE '%phenylephrine%' OR LOWER(drug) LIKE '%amiodarone%'
            OR LOWER(drug) LIKE '%lidocaine%' OR LOWER(drug) LIKE '%heparin%'
            OR LOWER(drug) LIKE '%enoxaparin%' OR LOWER(drug) LIKE '%argatroban%'
            OR LOWER(drug) LIKE '%propofol%' OR LOWER(drug) LIKE '%midazolam%'
            OR LOWER(drug) LIKE '%dexmedetomidine%'
            THEN drug
        END
      ) AS high_risk_drug_count
    FROM
      meds_first_7_days
    GROUP BY
      hadm_id
  ),
  readmission_data AS (
    WITH
      all_subject_admissions AS (
        SELECT
          a.subject_id,
          a.hadm_id,
          a.admittime,
          a.dischtime
        FROM
          `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        WHERE a.subject_id IN (SELECT subject_id FROM cohort_admissions)
      ),
      admissions_with_next_date AS (
        SELECT
          hadm_id,
          dischtime,
          LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
        FROM
          all_subject_admissions
      )
    SELECT
      hadm_id,
      CASE
        WHEN next_admittime IS NOT NULL AND DATETIME_DIFF(next_admittime, dischtime, DAY) <= 30
          THEN 1
        ELSE 0
      END AS was_readmitted_30_days
    FROM
      admissions_with_next_date
  ),
  full_cohort_data AS (
    SELECT
      ca.hadm_id,
      (
        COALESCE(cf.unique_drug_count, 0) + (2 * COALESCE(cf.high_risk_drug_count, 0))
        + COALESCE(cf.unique_route_count, 0)
      ) AS medication_complexity_score,
      DATETIME_DIFF(ca.dischtime, ca.admittime, DAY) AS los_days,
      ca.hospital_expire_flag,
      rd.was_readmitted_30_days
    FROM
      cohort_admissions AS ca
    LEFT JOIN
      complexity_features AS cf
      ON ca.hadm_id = cf.hadm_id
    LEFT JOIN
      readmission_data AS rd
      ON ca.hadm_id = rd.hadm_id
  ),
  stratified_data AS (
    SELECT
      *,
      NTILE(3) OVER (
        ORDER BY
          medication_complexity_score
      ) AS complexity_tertile
    FROM
      full_cohort_data
  )
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS patient_count,
  MIN(medication_complexity_score) AS min_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS in_hospital_mortality_percent,
  ROUND(AVG(was_readmitted_30_days) * 100, 2) AS readmission_rate_30day_percent
FROM
  stratified_data
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
