WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 51 AND 61
      AND ie.intime IS NOT NULL
  ),
  spo2_first_48h AS (
    SELECT
      pc.stay_id,
      pc.hadm_id,
      pc.subject_id,
      ce.valuenum
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid = 220277
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 50 AND 100
      AND ce.charttime BETWEEN pc.intime AND DATETIME_ADD(pc.intime, INTERVAL 48 HOUR)
  ),
  avg_spo2_per_stay AS (
    SELECT
      stay_id,
      hadm_id,
      subject_id,
      CASE
        WHEN AVG(valuenum) < 90 THEN '< 90%'
        WHEN AVG(valuenum) >= 90 AND AVG(valuenum) <= 92 THEN '90-92%'
        WHEN AVG(valuenum) > 92 AND AVG(valuenum) <= 95 THEN '93-95%'
        WHEN AVG(valuenum) > 95 THEN '> 95%'
        ELSE 'Unknown'
      END AS spo2_category
    FROM
      spo2_first_48h
    GROUP BY
      stay_id,
      hadm_id,
      subject_id
  ),
  aki_diagnoses AS (
    SELECT DISTINCT
      hadm_id,
      1 AS has_aki
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      icd_code LIKE '584%'
      OR icd_code LIKE 'N17%'
  )
SELECT
  spo2.spo2_category,
  COUNT(DISTINCT spo2.subject_id) AS patient_count,
  COUNT(DISTINCT CASE WHEN ad.has_aki = 1 THEN spo2.subject_id END) AS aki_patient_count,
  ROUND(
    100.0 * COUNT(DISTINCT CASE WHEN ad.has_aki = 1 THEN spo2.subject_id END)
    / COUNT(DISTINCT spo2.subject_id),
    2
  ) AS aki_rate_percent
FROM
  avg_spo2_per_stay AS spo2
LEFT JOIN
  aki_diagnoses AS ad ON spo2.hadm_id = ad.hadm_id
WHERE
  spo2.spo2_category != 'Unknown'
GROUP BY
  spo2.spo2_category
ORDER BY
  CASE
    WHEN spo2.spo2_category = '< 90%' THEN 1
    WHEN spo2.spo2_category = '90-92%' THEN 2
    WHEN spo2.spo2_category = '93-95%' THEN 3
    WHEN spo2.spo2_category = '> 95%' THEN 4
  END;
