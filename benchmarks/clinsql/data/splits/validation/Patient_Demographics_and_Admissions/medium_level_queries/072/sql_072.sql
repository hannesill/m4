WITH
  patient_cohort AS (
    SELECT
      a.hadm_id,
      a.discharge_location,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.services` AS s
      ON a.hadm_id = s.hadm_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 74 AND 84
      AND s.curr_service LIKE '%MED%'
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND s.transfertime = (
          SELECT MIN(s2.transfertime)
          FROM `physionet-data.mimiciv_3_1_hosp.services` s2
          WHERE s2.hadm_id = s.hadm_id
      )
  ),
  cohort_with_outcomes AS (
    SELECT
      length_of_stay_days,
      CASE
        WHEN hospital_expire_flag = 1
        THEN 'In-Hospital Mortality'
        WHEN discharge_location LIKE '%HOME%'
        THEN 'Discharged Home'
        WHEN discharge_location LIKE '%HOSPICE%'
        THEN 'Discharged to Hospice'
        ELSE 'Other'
      END AS discharge_outcome
    FROM
      patient_cohort
    WHERE length_of_stay_days >= 0
  )
SELECT
  discharge_outcome,
  COUNT(*) AS number_of_admissions,
  ROUND(AVG(length_of_stay_days), 2) AS mean_los_days,
  APPROX_QUANTILES(length_of_stay_days, 100)[OFFSET(50)] AS median_los_days,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(length_of_stay_days <= 5),
      COUNT(*)
    ),
    4
  ) AS percentile_rank_of_5_days
FROM
  cohort_with_outcomes
WHERE
  discharge_outcome IN ('Discharged Home', 'Discharged to Hospice', 'In-Hospital Mortality')
GROUP BY
  discharge_outcome
ORDER BY
  CASE
    WHEN discharge_outcome = 'Discharged Home' THEN 1
    WHEN discharge_outcome = 'Discharged to Hospice' THEN 2
    WHEN discharge_outcome = 'In-Hospital Mortality' THEN 3
  END;
