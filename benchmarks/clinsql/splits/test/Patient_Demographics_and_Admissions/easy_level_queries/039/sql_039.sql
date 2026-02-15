WITH PatientStays AS (
  SELECT
    p.subject_id,
    DATE_DIFF(DATE(icu.outtime), DATE(icu.intime), DAY) AS icu_length_of_stay,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime, icu.intime) AS admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON a.hadm_id = icu.hadm_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON a.hadm_id = d.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 43 AND 53
    AND icu.outtime IS NOT NULL
    AND icu.intime IS NOT NULL
    AND (
      d.icd_code LIKE '48%' OR d.icd_code LIKE 'J12%' OR d.icd_code LIKE 'J13%'
      OR d.icd_code LIKE 'J14%' OR d.icd_code LIKE 'J15%' OR d.icd_code LIKE 'J16%'
      OR d.icd_code LIKE 'J17%' OR d.icd_code LIKE 'J18%'
    )
)
SELECT
  APPROX_QUANTILES(icu_length_of_stay, 100)[OFFSET(25)] AS p25_icu_los_days
FROM
  PatientStays
WHERE
  admission_rank = 1
  AND icu_length_of_stay >= 0;
