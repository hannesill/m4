WITH
patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    ie.stay_id,
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
    AND ie.outtime IS NOT NULL
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 62 AND 72
),
avg_hr_per_stay AS (
  SELECT
    pc.subject_id,
    pc.hadm_id,
    pc.stay_id,
    AVG(ce.valuenum) AS avg_heart_rate
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    ON pc.stay_id = ce.stay_id
  WHERE
    ce.itemid IN (220045, 211)
    AND ce.valuenum IS NOT NULL
    AND ce.valuenum BETWEEN 30 AND 250
  GROUP BY
    pc.subject_id,
    pc.hadm_id,
    pc.stay_id
),
categorized_stays AS (
  SELECT
    subject_id,
    hadm_id,
    stay_id,
    avg_heart_rate,
    CASE
      WHEN avg_heart_rate < 60 THEN '1. Bradycardia (<60 bpm)'
      WHEN avg_heart_rate >= 60 AND avg_heart_rate < 100 THEN '2. Normal (60-99 bpm)'
      WHEN avg_heart_rate >= 100 AND avg_heart_rate < 120 THEN '3. Tachycardia (100-119 bpm)'
      WHEN avg_heart_rate >= 120 THEN '4. Severe Tachycardia (>=120 bpm)'
      ELSE 'Unknown'
    END AS hr_category
  FROM
    avg_hr_per_stay
),
mi_diagnoses AS (
  SELECT DISTINCT
    hadm_id
  FROM
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
  WHERE
    (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
    OR
    (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I21')
)
SELECT
  cs.hr_category,
  COUNT(DISTINCT cs.subject_id) AS patient_count,
  COUNT(DISTINCT CASE WHEN mi.hadm_id IS NOT NULL THEN cs.subject_id END) AS mi_patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT CASE WHEN mi.hadm_id IS NOT NULL THEN cs.subject_id END)
    / COUNT(DISTINCT cs.subject_id),
    2
  ) AS mi_rate_percent
FROM
  categorized_stays AS cs
LEFT JOIN
  mi_diagnoses AS mi
  ON cs.hadm_id = mi.hadm_id
WHERE
  cs.hr_category != 'Unknown'
GROUP BY
  cs.hr_category
ORDER BY
  cs.hr_category;
