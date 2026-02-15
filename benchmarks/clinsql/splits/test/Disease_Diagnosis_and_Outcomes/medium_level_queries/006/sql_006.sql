WITH
  sepsis_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.hospital_expire_flag,
      (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) AS age_at_admission,
      GREATEST(0, DATETIME_DIFF(a.dischtime, a.admittime, DAY)) AS length_of_stay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) BETWEEN 64 AND 74
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            d.icd_code = '99591'
            OR d.icd_code LIKE 'A41%'
          )
      )
      AND NOT EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            d.icd_code = '78552'
            OR d.icd_code = 'R6521'
          )
      )
  ),
  cohort_with_comorbidities AS (
    SELECT
      sc.hadm_id,
      sc.hospital_expire_flag,
      sc.length_of_stay,
      MAX(
        CASE
          WHEN d.icd_code LIKE 'N18%'
          OR d.icd_code LIKE '585%' THEN 1
          ELSE 0
        END
      ) AS has_ckd,
      MAX(
        CASE
          WHEN d.icd_code LIKE '250%'
          OR d.icd_code LIKE 'E08%'
          OR d.icd_code LIKE 'E09%'
          OR d.icd_code LIKE 'E10%'
          OR d.icd_code LIKE 'E11%'
          OR d.icd_code LIKE 'E13%' THEN 1
          ELSE 0
        END
      ) AS has_diabetes
    FROM
      sepsis_cohort AS sc
      LEFT JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON sc.hadm_id = d.hadm_id
    GROUP BY
      sc.hadm_id,
      sc.hospital_expire_flag,
      sc.length_of_stay
  ),
  cohort_with_quartiles AS (
    SELECT
      cwc.*,
      NTILE(4) OVER (
        ORDER BY
          cwc.length_of_stay
      ) AS los_quartile
    FROM
      cohort_with_comorbidities AS cwc
  )
SELECT
  los_quartile,
  COUNT(hadm_id) AS total_admissions,
  CONCAT(
    CAST(MIN(length_of_stay) AS STRING),
    ' - ',
    CAST(MAX(length_of_stay) AS STRING)
  ) AS los_range_days,
  ROUND(AVG(length_of_stay), 1) AS avg_los_days,
  ROUND(
    AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100,
    2
  ) AS mortality_rate_percent,
  ROUND(AVG(CAST(has_ckd AS FLOAT64)) * 100, 2) AS ckd_prevalence_percent,
  ROUND(
    AVG(CAST(has_diabetes AS FLOAT64)) * 100,
    2
  ) AS diabetes_prevalence_percent
FROM
  cohort_with_quartiles
GROUP BY
  los_quartile
ORDER BY
  los_quartile;
