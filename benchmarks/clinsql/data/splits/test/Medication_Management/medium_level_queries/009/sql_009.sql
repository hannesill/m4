WITH
cohort_admissions AS (
  SELECT DISTINCT
    pat.subject_id,
    adm.hadm_id,
    adm.admittime,
    adm.dischtime
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS pat
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
    ON pat.subject_id = adm.subject_id
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx_diabetes
    ON adm.hadm_id = dx_diabetes.hadm_id
  JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx_hf
    ON adm.hadm_id = dx_hf.hadm_id
  WHERE
    pat.gender = 'M'
    AND adm.admittime IS NOT NULL AND adm.dischtime IS NOT NULL
    AND DATETIME_DIFF(adm.dischtime, adm.admittime, HOUR) >= 48
    AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 68 AND 78
    AND (dx_diabetes.icd_code LIKE '250%' OR dx_diabetes.icd_code LIKE 'E10%' OR dx_diabetes.icd_code LIKE 'E11%')
    AND (dx_hf.icd_code LIKE '428%' OR dx_hf.icd_code LIKE 'I50%')
),
medication_initiations AS (
  SELECT
    ca.hadm_id,
    CASE
      WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
      ELSE 'Oral Agents'
    END AS medication_class,
    MIN(rx.starttime) AS first_starttime
  FROM cohort_admissions AS ca
  JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
    ON ca.hadm_id = rx.hadm_id
  WHERE
    rx.starttime IS NOT NULL
    AND rx.starttime BETWEEN ca.admittime AND ca.dischtime
    AND (
      LOWER(rx.drug) LIKE '%insulin%'
      OR LOWER(rx.drug) LIKE '%metformin%'
      OR LOWER(rx.drug) LIKE '%glipizide%'
      OR LOWER(rx.drug) LIKE '%glyburide%'
      OR LOWER(rx.drug) LIKE '%sitagliptin%'
      OR LOWER(rx.drug) LIKE '%linagliptin%'
    )
  GROUP BY
    ca.hadm_id,
    medication_class
),
initiation_counts AS (
  SELECT
    mi.medication_class,
    COUNT(DISTINCT CASE
      WHEN DATETIME_DIFF(mi.first_starttime, ca.admittime, HOUR) <= 24 THEN ca.hadm_id
    END) AS initiated_first_24h_count,
    COUNT(DISTINCT CASE
      WHEN DATETIME_DIFF(ca.dischtime, mi.first_starttime, HOUR) <= 24 THEN ca.hadm_id
    END) AS initiated_last_24h_count
  FROM cohort_admissions AS ca
  JOIN medication_initiations AS mi
    ON ca.hadm_id = mi.hadm_id
  GROUP BY
    mi.medication_class
)
SELECT
  all_classes.medication_class,
  total_cohort.total_admissions AS total_patients_in_cohort,
  COALESCE(ic.initiated_first_24h_count, 0) AS initiated_first_24h_count,
  COALESCE(ic.initiated_last_24h_count, 0) AS initiated_last_24h_count,
  ROUND(
    (COALESCE(ic.initiated_first_24h_count, 0) * 100.0) / total_cohort.total_admissions,
    2
  ) AS pct_initiated_first_24h,
  ROUND(
    (COALESCE(ic.initiated_last_24h_count, 0) * 100.0) / total_cohort.total_admissions,
    2
  ) AS pct_initiated_last_24h,
  ROUND(
    ((COALESCE(ic.initiated_last_24h_count, 0) * 100.0) / total_cohort.total_admissions) -
    ((COALESCE(ic.initiated_first_24h_count, 0) * 100.0) / total_cohort.total_admissions),
    2
  ) AS absolute_difference_pp
FROM
  (SELECT 'Insulin' AS medication_class UNION ALL SELECT 'Oral Agents' AS medication_class) AS all_classes
CROSS JOIN
  (SELECT COUNT(*) AS total_admissions FROM cohort_admissions) AS total_cohort
LEFT JOIN
  initiation_counts AS ic ON all_classes.medication_class = ic.medication_class
ORDER BY
  all_classes.medication_class;
