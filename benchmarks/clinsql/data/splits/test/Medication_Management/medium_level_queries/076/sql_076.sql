WITH patient_cohort AS (
  SELECT DISTINCT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d1
    ON a.hadm_id = d1.hadm_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d2
    ON a.hadm_id = d2.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 75 AND 85
    AND (
      d1.icd_code LIKE '250%'
      OR d1.icd_code LIKE 'E10%'
      OR d1.icd_code LIKE 'E11%'
    )
    AND (
      d2.icd_code LIKE '428%'
      OR d2.icd_code LIKE 'I50%'
    )
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 36
),
glp1_initiations AS (
  SELECT
    pc.hadm_id,
    CASE
      WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 24 THEN 1
      ELSE 0
    END AS initiated_first_24h,
    CASE
      WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12 THEN 1
      ELSE 0
    END AS initiated_last_12h
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
    )
    AND LOWER(rx.route) IN ('sc', 'iv', 'iv drip', 'iv bolus')
    AND rx.starttime IS NOT NULL
    AND rx.starttime >= pc.admittime
    AND rx.starttime <= pc.dischtime
),
admission_flags AS (
  SELECT
    hadm_id,
    MAX(initiated_first_24h) AS was_initiated_first_24h,
    MAX(initiated_last_12h) AS was_initiated_last_12h
  FROM
    glp1_initiations
  GROUP BY
    hadm_id
)
SELECT
  ROUND(
    SUM(IFNULL(af.was_initiated_first_24h, 0)) * 100.0 / COUNT(pc.hadm_id),
    2
  ) AS initiation_rate_first_24h_pct,
  ROUND(
    SUM(IFNULL(af.was_initiated_last_12h, 0)) * 100.0 / COUNT(pc.hadm_id),
    2
  ) AS initiation_rate_last_12h_pct
FROM
  patient_cohort AS pc
LEFT JOIN
  admission_flags AS af
  ON pc.hadm_id = af.hadm_id;
