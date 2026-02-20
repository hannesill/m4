WITH
  copd_female_admissions AS (
    SELECT DISTINCT
      diag.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag
      ON pat.subject_id = diag.subject_id
    WHERE
      pat.gender = 'F'
      AND (
        diag.icd_code LIKE '490%'
        OR diag.icd_code LIKE '491%'
        OR diag.icd_code LIKE '492%'
        OR diag.icd_code LIKE '496%'
        OR diag.icd_code LIKE 'J44%'
      )
  ),
  nadir_sodium_per_stay AS (
    SELECT
      cfa.hadm_id,
      MIN(le.valuenum) AS nadir_sodium
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    INNER JOIN
      copd_female_admissions AS cfa
      ON le.hadm_id = cfa.hadm_id
    WHERE
      le.itemid = 50983
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 120 AND 160
    GROUP BY
      cfa.hadm_id
  )
SELECT
  ROUND(STDDEV(nsp.nadir_sodium), 2) AS stddev_of_nadir_sodium
FROM
  nadir_sodium_per_stay AS nsp;
