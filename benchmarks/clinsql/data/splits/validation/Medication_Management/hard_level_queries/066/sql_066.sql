WITH
  transplant_cohort AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 43 AND 53
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            (d.icd_version = 9 AND d.icd_code LIKE 'V42%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'Z94%')
          )
      )
  ),
  meds_first_7_days AS (
    SELECT
      pr.hadm_id,
      pr.drug,
      pr.route,
      CASE
        WHEN LOWER(pr.drug) LIKE '%heparin%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%warfarin%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%enoxaparin%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%apixaban%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%rivaroxaban%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%insulin%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%norepinephrine%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%epinephrine%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%vasopressin%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%phenylephrine%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%dopamine%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%tacrolimus%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%cyclosporine%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%mycophenolate%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%prednisone%' THEN 1
        WHEN LOWER(pr.drug) LIKE '%sirolimus%' THEN 1
        ELSE 0
      END AS is_high_risk_drug
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
    INNER JOIN
      transplant_cohort AS tc
      ON pr.hadm_id = tc.hadm_id
    WHERE
      pr.starttime >= tc.admittime AND pr.starttime <= DATETIME_ADD(tc.admittime, INTERVAL 7 DAY)
  ),
  complexity_scores AS (
    SELECT
      hadm_id,
      (
        (COUNT(DISTINCT drug) * 1)
        + (COUNT(DISTINCT route) * 2)
        + (COUNT(DISTINCT CASE WHEN is_high_risk_drug = 1 THEN drug END) * 3)
      ) AS medication_complexity_score
    FROM
      meds_first_7_days
    GROUP BY
      hadm_id
  ),
  readmission_flags AS (
    SELECT
      a.hadm_id,
      LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    WHERE
      a.subject_id IN (
        SELECT DISTINCT subject_id FROM transplant_cohort
      )
  ),
  patient_outcomes AS (
    SELECT
      tc.hadm_id,
      tc.hospital_expire_flag,
      DATETIME_DIFF(tc.dischtime, tc.admittime, DAY) AS los_days,
      CASE
        WHEN rf.next_admittime IS NOT NULL AND DATETIME_DIFF(rf.next_admittime, tc.dischtime, DAY) <= 30 THEN 1
        ELSE 0
      END AS readmitted_30_days_flag,
      COALESCE(cs.medication_complexity_score, 0) AS medication_complexity_score,
      NTILE(4) OVER (ORDER BY COALESCE(cs.medication_complexity_score, 0)) AS complexity_quartile
    FROM
      transplant_cohort AS tc
    LEFT JOIN
      complexity_scores AS cs
      ON tc.hadm_id = cs.hadm_id
    LEFT JOIN
      readmission_flags AS rf
      ON tc.hadm_id = rf.hadm_id
  )
SELECT
  complexity_quartile,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_length_of_stay_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS in_hospital_mortality_rate_pct,
  ROUND(AVG(readmitted_30_days_flag) * 100, 2) AS readmission_30_day_rate_pct
FROM
  patient_outcomes
GROUP BY
  complexity_quartile
ORDER BY
  complexity_quartile;
