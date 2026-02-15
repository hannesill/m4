WITH sepsis_admissions AS (
  SELECT DISTINCT
    d.hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    ON p.subject_id = d.subject_id
  WHERE
    p.gender = 'M'
    AND
    (
      (d.icd_version = 9 AND d.icd_code IN ('99591', '99592'))
      OR
      (d.icd_version = 10 AND d.icd_code LIKE 'A41%')
    )
),
peak_platelets_per_stay AS (
  SELECT
    sa.hadm_id,
    MAX(le.valuenum) AS peak_platelet_count
  FROM sepsis_admissions AS sa
  JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON sa.hadm_id = le.hadm_id
  WHERE
    le.itemid = 51265
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 10 AND 1000
  GROUP BY
    sa.hadm_id
)
SELECT
  ROUND(APPROX_QUANTILES(peak_platelet_count, 100)[OFFSET(75)], 0) AS p75_peak_platelet_count
FROM peak_platelets_per_stay;
