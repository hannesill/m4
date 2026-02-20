WITH
  patient_cohort AS (
    SELECT DISTINCT
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
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 53 AND 63
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
  medication_events AS (
    SELECT
      c.hadm_id,
      MAX(
        CASE
          WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) BETWEEN 0 AND 24
          THEN 1
          ELSE 0
        END
      ) AS given_in_first_24h,
      MAX(
        CASE
          WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 12
          THEN 1
          ELSE 0
        END
      ) AS given_in_final_12h
    FROM
      patient_cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      (
        LOWER(rx.drug) LIKE '%semaglutide%'
        OR LOWER(rx.drug) LIKE '%liraglutide%'
        OR LOWER(rx.drug) LIKE '%dulaglutide%'
        OR LOWER(rx.drug) LIKE '%exenatide%'
      )
      AND rx.starttime IS NOT NULL
      AND rx.starttime >= c.admittime
      AND rx.starttime <= c.dischtime
    GROUP BY
      c.hadm_id
  )
SELECT
  ROUND(
    (
      SELECT
        COUNT(hadm_id)
      FROM
        medication_events
      WHERE
        given_in_first_24h = 1
    ) * 100.0 / (
      SELECT
        COUNT(hadm_id)
      FROM
        patient_cohort
    ),
    2
  ) AS initiation_rate_first_24h_pct,
  ROUND(
    (
      SELECT
        COUNT(hadm_id)
      FROM
        medication_events
      WHERE
        given_in_final_12h = 1
    ) * 100.0 / (
      SELECT
        COUNT(hadm_id)
      FROM
        patient_cohort
    ),
    2
  ) AS initiation_rate_final_12h_pct;
