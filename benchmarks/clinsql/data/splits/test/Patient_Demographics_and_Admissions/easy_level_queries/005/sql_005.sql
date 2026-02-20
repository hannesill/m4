WITH FirstDialysisIcuStay AS (
  SELECT
    p.subject_id,
    icu.los,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime, icu.intime) as stay_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON a.hadm_id = icu.hadm_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc ON a.hadm_id = proc.hadm_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 77 AND 87
    AND proc.icd_code IN (
      '3995',
      '5498',
      '5A1D00Z',
      '5A1D60Z'
      )
    AND icu.los IS NOT NULL
    AND icu.los > 0
)
SELECT
  (APPROX_QUANTILES(los, 100)[OFFSET(75)] - APPROX_QUANTILES(los, 100)[OFFSET(25)]) AS iqr_icu_los_days
FROM
  FirstDialysisIcuStay
WHERE
  stay_rank = 1;
