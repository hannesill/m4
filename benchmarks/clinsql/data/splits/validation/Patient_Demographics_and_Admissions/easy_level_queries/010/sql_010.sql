WITH
  aki_icu_stays AS (
    SELECT DISTINCT
      icu.stay_id,
      DATE_DIFF(DATE(icu.outtime), DATE(icu.intime), DAY) AS icu_los_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx ON a.hadm_id = dx.hadm_id
      JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON a.hadm_id = icu.hadm_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 48 AND 58
      AND (
        (dx.icd_version = 9 AND dx.icd_code LIKE '584%')
        OR (dx.icd_version = 10 AND dx.icd_code LIKE 'N17%')
      )
      AND icu.outtime IS NOT NULL
      AND DATE_DIFF(DATE(icu.outtime), DATE(icu.intime), DAY) >= 0
  )
SELECT
  APPROX_QUANTILES(icu_los_days, 100)[OFFSET(25)] AS p25_icu_length_of_stay_days
FROM
  aki_icu_stays;
