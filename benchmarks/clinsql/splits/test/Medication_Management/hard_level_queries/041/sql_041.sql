WITH
  cohort_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)
      ) BETWEEN 40 AND 50
      AND a.hadm_id IN (
        SELECT DISTINCT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          (icd_version = 9 AND icd_code LIKE '428%')
          OR (icd_version = 10 AND icd_code LIKE 'I50%')
      )
  ),
  medication_complexity AS (
    SELECT
      c.hadm_id,
      (
        COUNT(DISTINCT p.drug) + (
          2 * COUNT(
            DISTINCT CASE
              WHEN LOWER(p.drug) LIKE '%heparin%' OR LOWER(p.drug) LIKE '%warfarin%' OR LOWER(p.drug) LIKE '%enoxaparin%'
              OR LOWER(p.drug) LIKE '%lovenox%' OR LOWER(p.drug) LIKE '%argatroban%' OR LOWER(p.drug) LIKE '%bivalirudin%'
              OR LOWER(p.drug) LIKE '%fondaparinux%' OR LOWER(p.drug) LIKE '%rivaroxaban%' OR LOWER(p.drug) LIKE '%apixaban%'
              OR LOWER(p.drug) LIKE '%dabigatran%'
              OR LOWER(p.drug) LIKE '%amiodarone%' OR LOWER(p.drug) LIKE '%lidocaine%' OR LOWER(p.drug) LIKE '%procainamide%'
              OR LOWER(p.drug) LIKE '%dofetilide%' OR LOWER(p.drug) LIKE '%sotalol%'
              OR LOWER(p.drug) LIKE '%norepinephrine%' OR LOWER(p.drug) LIKE '%epinephrine%' OR LOWER(p.drug) LIKE '%dopamine%'
              OR LOWER(p.drug) LIKE '%dobutamine%' OR LOWER(p.drug) LIKE '%vasopressin%' OR LOWER(p.drug) LIKE '%phenylephrine%'
              OR LOWER(p.drug) LIKE '%milrinone%'
              OR LOWER(p.drug) LIKE '%insulin%' THEN p.drug
              ELSE NULL
            END
          )
        ) + COUNT(DISTINCT p.route)
      ) AS medication_complexity_score
    FROM
      cohort_admissions AS c
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS p ON c.hadm_id = p.hadm_id
    WHERE
      p.starttime >= c.admittime AND p.starttime <= DATETIME_ADD(c.admittime, INTERVAL 7 DAY)
    GROUP BY
      c.hadm_id
  ),
  complexity_quintiles AS (
    SELECT
      hadm_id,
      medication_complexity_score,
      NTILE(5) OVER (
        ORDER BY
          medication_complexity_score
      ) AS complexity_quintile
    FROM
      medication_complexity
  ),
  readmission_flags AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(
          LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime),
          dischtime,
          DAY
        ) <= 30 THEN 1
        ELSE 0
      END AS readmitted_30_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  )
SELECT
  cq.complexity_quintile,
  COUNT(DISTINCT ca.hadm_id) AS num_patients,
  MIN(cq.medication_complexity_score) AS min_complexity_score,
  MAX(cq.medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(cq.medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(DATETIME_DIFF(ca.dischtime, ca.admittime, HOUR) / 24.0), 2) AS avg_los_days,
  ROUND(AVG(ca.hospital_expire_flag), 4) AS mortality_rate,
  ROUND(AVG(COALESCE(rf.readmitted_30_days, 0)), 4) AS readmission_rate_30_day
FROM
  cohort_admissions AS ca
  INNER JOIN complexity_quintiles AS cq ON ca.hadm_id = cq.hadm_id
  LEFT JOIN readmission_flags AS rf ON ca.hadm_id = rf.hadm_id
GROUP BY
  cq.complexity_quintile
ORDER BY
  cq.complexity_quintile;
