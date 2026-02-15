WITH
  female_patient_cohort AS (
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
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 41 AND 51
      AND ie.intime IS NOT NULL
  ),
  rr_measurements_first_48h AS (
    SELECT
      fpc.stay_id,
      fpc.subject_id,
      fpc.hadm_id,
      ce.valuenum
    FROM
      female_patient_cohort AS fpc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON fpc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220210, 615)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
      AND ce.valuenum < 100
      AND ce.charttime BETWEEN fpc.intime AND DATETIME_ADD(fpc.intime, INTERVAL 48 HOUR)
  ),
  avg_rr_per_stay AS (
    SELECT
      subject_id,
      hadm_id,
      stay_id,
      AVG(valuenum) AS avg_rr
    FROM
      rr_measurements_first_48h
    GROUP BY
      subject_id,
      hadm_id,
      stay_id
  ),
  stroke_diagnoses AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      SUBSTR(icd_code, 1, 3) IN ('430', '431', '432', '433', '434', '435', '436', '437', '438')
      OR SUBSTR(icd_code, 1, 2) = 'I6'
  ),
  final_cohort_data AS (
    SELECT
      rr.subject_id,
      rr.hadm_id,
      CASE
        WHEN rr.avg_rr < 12 THEN '< 12 (Bradypnea)'
        WHEN rr.avg_rr >= 12 AND rr.avg_rr <= 20 THEN '12-20 (Normal)'
        WHEN rr.avg_rr >= 21 AND rr.avg_rr <= 29 THEN '21-29 (Tachypnea)'
        WHEN rr.avg_rr >= 30 THEN '>= 30 (Severe Tachypnea)'
        ELSE 'Unknown'
      END AS rr_category,
      CASE
        WHEN sd.hadm_id IS NOT NULL THEN 1
        ELSE 0
      END AS had_stroke
    FROM
      avg_rr_per_stay AS rr
    LEFT JOIN
      stroke_diagnoses AS sd
      ON rr.hadm_id = sd.hadm_id
  )
SELECT
  rr_category,
  COUNT(DISTINCT subject_id) AS patient_count,
  SUM(had_stroke) AS stroke_patient_count,
  ROUND(
    100.0 * SUM(had_stroke) / COUNT(DISTINCT subject_id),
    2
  ) AS stroke_rate_percent
FROM
  final_cohort_data
WHERE
  rr_category != 'Unknown'
GROUP BY
  rr_category
ORDER BY
  CASE
    WHEN rr_category = '< 12 (Bradypnea)' THEN 1
    WHEN rr_category = '12-20 (Normal)' THEN 2
    WHEN rr_category = '21-29 (Tachypnea)' THEN 3
    WHEN rr_category = '>= 30 (Severe Tachypnea)' THEN 4
  END;
