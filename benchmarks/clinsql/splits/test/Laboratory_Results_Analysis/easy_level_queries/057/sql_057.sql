WITH pneumonia_admissions AS (
  SELECT DISTINCT
    diag.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON diag.subject_id = p.subject_id
  WHERE
    p.gender = 'M'
    AND
    (
      (diag.icd_version = 9 AND SUBSTR(diag.icd_code, 1, 3) BETWEEN '480' AND '486')
      OR
      (diag.icd_version = 10 AND SUBSTR(diag.icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
    )
),

nadir_creatinine_per_stay AS (
  SELECT
    pa.hadm_id,
    MIN(le.valuenum) AS nadir_creatinine
  FROM pneumonia_admissions AS pa
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON pa.hadm_id = le.hadm_id
  WHERE
    le.itemid = 50912
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 0.5 AND 10
  GROUP BY
    pa.hadm_id
)
SELECT
  ROUND(
    (APPROX_QUANTILES(nadir_creatinine, 4)[OFFSET(3)] - APPROX_QUANTILES(nadir_creatinine, 4)[OFFSET(1)]),
    2
  ) AS iqr_nadir_serum_creatinine
FROM nadir_creatinine_per_stay;
