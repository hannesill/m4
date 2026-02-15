WITH hf_admissions AS (
  SELECT DISTINCT
    diag.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` diag
    ON p.subject_id = diag.subject_id
  WHERE
    p.gender = 'M'
    AND (
      diag.icd_code LIKE '428%'
      OR diag.icd_code LIKE 'I50%'
    )
),
nadir_hemoglobin_per_stay AS (
  SELECT
    le.hadm_id,
    MIN(le.valuenum) AS nadir_hgb
  FROM `physionet-data.mimiciv_3_1_hosp.labevents` le
  INNER JOIN hf_admissions hf
    ON le.hadm_id = hf.hadm_id
  WHERE
    le.itemid = 51222
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 7 AND 18
  GROUP BY
    le.hadm_id
)
SELECT
  ROUND(
    APPROX_QUANTILES(nadir_hgb, 100)[OFFSET(75)],
    2
  ) AS p75_nadir_hemoglobin
FROM nadir_hemoglobin_per_stay;
