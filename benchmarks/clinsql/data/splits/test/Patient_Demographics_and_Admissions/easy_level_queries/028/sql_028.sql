WITH SepsisAdmissions AS (
  SELECT DISTINCT adm.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    ON adm.subject_id = pat.subject_id
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON adm.hadm_id = dx.hadm_id
  WHERE
    pat.gender = 'M'
    AND pat.anchor_age BETWEEN 90 AND 100
    AND (
      (dx.icd_version = 9 AND dx.icd_code IN ('99591', '99592', '78552'))
      OR (dx.icd_version = 10 AND (dx.icd_code LIKE 'A41%' OR dx.icd_code LIKE 'R65.2%'))
    )
)
SELECT
  STDDEV_SAMP(icu.los) AS stddev_icu_los_days
FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
JOIN SepsisAdmissions
  ON icu.hadm_id = SepsisAdmissions.hadm_id
WHERE
  icu.los IS NOT NULL AND icu.los > 0;
