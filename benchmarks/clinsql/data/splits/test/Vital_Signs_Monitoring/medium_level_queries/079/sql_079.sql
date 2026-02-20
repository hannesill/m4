WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
      ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'M'
      AND ie.intime IS NOT NULL
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 40 AND 50
  ),
  sbp_first_48h AS (
    SELECT
      pc.stay_id,
      pc.hadm_id,
      ce.valuenum
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220050, 220179)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 50 AND 300
      AND DATETIME_DIFF(ce.charttime, pc.intime, HOUR) BETWEEN 0 AND 48
  ),
  stay_avg_sbp_categorized AS (
    SELECT
      stay_id,
      hadm_id,
      CASE
        WHEN AVG(valuenum) < 140 THEN '< 140 mmHg'
        WHEN AVG(valuenum) >= 140 AND AVG(valuenum) < 160 THEN '140-159 mmHg'
        WHEN AVG(valuenum) >= 160 THEN '>= 160 mmHg'
        ELSE NULL
      END AS sbp_category
    FROM
      sbp_first_48h
    GROUP BY
      stay_id,
      hadm_id
  ),
  mi_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE '410%'
      OR icd_code LIKE 'I21%'
  ),
  aggregated_data AS (
    SELECT
      s.stay_id,
      s.sbp_category,
      CASE
        WHEN mi.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS has_mi
    FROM
      stay_avg_sbp_categorized AS s
    LEFT JOIN
      mi_admissions AS mi
      ON s.hadm_id = mi.hadm_id
    WHERE s.sbp_category IS NOT NULL
  )
SELECT
  ad.sbp_category,
  COUNT(ad.stay_id) AS total_patients_in_category,
  ROUND(
    COUNT(ad.stay_id) * 100.0 / SUM(COUNT(ad.stay_id)) OVER (),
    2
  ) AS percent_of_total_patients,
  SUM(ad.has_mi) AS mi_patient_count,
  ROUND(
    SUM(ad.has_mi) * 100.0 / COUNT(ad.stay_id),
    2
  ) AS mi_rate_percent
FROM
  aggregated_data AS ad
GROUP BY
  ad.sbp_category
ORDER BY
  CASE
    WHEN ad.sbp_category = '< 140 mmHg' THEN 1
    WHEN ad.sbp_category = '140-159 mmHg' THEN 2
    WHEN ad.sbp_category = '>= 160 mmHg' THEN 3
  END;
