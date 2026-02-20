WITH
  dka_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      STARTS_WITH(icd_code, '2501')
      OR STARTS_WITH(icd_code, 'E101')
      OR STARTS_WITH(icd_code, 'E111')
      OR STARTS_WITH(icd_code, 'E131')
  ),
  peak_glucose_per_stay AS (
    SELECT
      le.hadm_id,
      MAX(le.valuenum) AS peak_glucose
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN dka_admissions AS dka ON le.hadm_id = dka.hadm_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON le.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND le.itemid = 50931
      AND le.valuenum IS NOT NULL
      AND le.valuenum BETWEEN 50 AND 500
    GROUP BY
      le.hadm_id
  )
SELECT
  ROUND(
    APPROX_QUANTILES(peak_glucose, 2)[OFFSET(1)],
    2
  ) AS median_peak_glucose_dka
FROM
  peak_glucose_per_stay;
