WITH
  copd_admissions AS (
    SELECT DISTINCT
      d.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON d.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (
        d.icd_code LIKE '490%'
        OR d.icd_code LIKE '491%'
        OR d.icd_code LIKE '492%'
        OR d.icd_code LIKE '496%'
        OR d.icd_code LIKE 'J40%'
        OR d.icd_code LIKE 'J41%'
        OR d.icd_code LIKE 'J42%'
        OR d.icd_code LIKE 'J43%'
        OR d.icd_code LIKE 'J44%'
      )
  ),
  peak_creatinine_per_stay AS (
    SELECT
      le.hadm_id,
      MAX(le.valuenum) AS peak_creatinine
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    WHERE
      le.hadm_id IN (SELECT hadm_id FROM copd_admissions)
      AND le.itemid = 50912
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 0.5 AND 10
    GROUP BY
      le.hadm_id
  )
SELECT
  ROUND(MAX(peak_creatinine), 2) AS max_of_peak_creatinine
FROM
  peak_creatinine_per_stay;
