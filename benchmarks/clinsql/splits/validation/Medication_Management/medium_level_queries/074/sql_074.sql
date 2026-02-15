WITH
  patient_cohort AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes
      ON a.hadm_id = d_diabetes.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
      ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 48 AND 58
      AND (
        d_diabetes.icd_code LIKE '250%'
        OR d_diabetes.icd_code LIKE 'E10%'
        OR d_diabetes.icd_code LIKE 'E11%'
      )
      AND (
        d_hf.icd_code LIKE '428%'
        OR d_hf.icd_code LIKE 'I50%'
      )
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 36
  ),
  glp1_timed_prescriptions AS (
    SELECT
      pc.hadm_id,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 24 THEN 1
        ELSE 0
      END AS given_in_first_24h,
      CASE
        WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12 THEN 1
        ELSE 0
      END AS given_in_final_12h
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON pc.hadm_id = rx.hadm_id
    WHERE
      (
        LOWER(rx.drug) LIKE '%liraglutide%'
        OR LOWER(rx.drug) LIKE '%semaglutide%'
        OR LOWER(rx.drug) LIKE '%dulaglutide%'
        OR LOWER(rx.drug) LIKE '%exenatide%'
        OR LOWER(rx.drug) LIKE '%lixisenatide%'
      )
      AND LOWER(rx.route) = 'sc'
      AND rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN pc.admittime AND pc.dischtime
  ),
  admission_level_exposure AS (
    SELECT
      hadm_id,
      MAX(given_in_first_24h) AS exposed_in_first_24h,
      MAX(given_in_final_12h) AS exposed_in_final_12h
    FROM
      glp1_timed_prescriptions
    GROUP BY
      hadm_id
  ),
  final_counts AS (
    SELECT
      COUNT(pc.hadm_id) AS total_admissions,
      COUNTIF(ale.exposed_in_first_24h = 1) AS admissions_exposed_first_24h,
      COUNTIF(ale.exposed_in_final_12h = 1) AS admissions_exposed_final_12h
    FROM
      patient_cohort AS pc
    LEFT JOIN
      admission_level_exposure AS ale
      ON pc.hadm_id = ale.hadm_id
  )
SELECT
  ROUND(
    (admissions_exposed_first_24h * 100.0) / NULLIF(total_admissions, 0),
    2
  ) AS prevalence_first_24h_pct,
  ROUND(
    (admissions_exposed_final_12h * 100.0) / NULLIF(total_admissions, 0),
    2
  ) AS prevalence_final_12h_pct
FROM
  final_counts;
