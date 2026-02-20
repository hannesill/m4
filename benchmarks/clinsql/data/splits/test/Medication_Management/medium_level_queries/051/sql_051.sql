WITH patient_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    a.admittime,
    a.dischtime,
    (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_code LIKE '250%' OR icd_code LIKE 'E10%' OR icd_code LIKE 'E11%')
      OR (icd_code LIKE '428%' OR icd_code LIKE 'I50%')
    GROUP BY
      hadm_id
    HAVING
      COUNT(DISTINCT CASE WHEN icd_code LIKE '250%' OR icd_code LIKE 'E10%' OR icd_code LIKE 'E11%' THEN 1 END) > 0
      AND COUNT(DISTINCT CASE WHEN icd_code LIKE '428%' OR icd_code LIKE 'I50%' THEN 1 END) > 0
  ) AS dx
  ON a.hadm_id = dx.hadm_id
  WHERE
    p.gender = 'F'
    AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 86 AND 96
    AND a.dischtime IS NOT NULL
    AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
),
medication_windows AS (
  SELECT DISTINCT
    pc.hadm_id,
    CASE
      WHEN LOWER(rx.drug) LIKE '%insulin%' THEN 'Insulin'
      WHEN LOWER(rx.drug) IN ('metformin', 'glipizide', 'glyburide', 'sitagliptin', 'linagliptin') THEN 'Oral Agents'
    END AS med_class,
    CASE
      WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 12 THEN 'Early'
      WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 72 THEN 'Late'
    END AS prescription_window
  FROM
    patient_cohort AS pc
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
    ON pc.hadm_id = rx.hadm_id
  WHERE
    rx.starttime IS NOT NULL
    AND rx.starttime BETWEEN pc.admittime AND pc.dischtime
    AND (
      LOWER(rx.drug) LIKE '%insulin%'
      OR LOWER(rx.drug) IN ('metformin', 'glipizide', 'glyburide', 'sitagliptin', 'linagliptin')
    )
    AND CASE
      WHEN DATETIME_DIFF(rx.starttime, pc.admittime, HOUR) BETWEEN 0 AND 12 THEN 'Early'
      WHEN DATETIME_DIFF(pc.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 72 THEN 'Late'
    END IS NOT NULL
),
patient_window_flags AS (
  SELECT
    hadm_id,
    med_class,
    MAX(IF(prescription_window = 'Early', 1, 0)) AS on_early,
    MAX(IF(prescription_window = 'Late', 1, 0)) AS on_late
  FROM
    medication_windows
  GROUP BY
    hadm_id,
    med_class
),
full_patient_status AS (
  SELECT
    pc.hadm_id,
    mc.med_class,
    IFNULL(pwf.on_early, 0) AS on_early,
    IFNULL(pwf.on_late, 0) AS on_late
  FROM
    patient_cohort AS pc
  CROSS JOIN (
    SELECT 'Insulin' AS med_class UNION ALL
    SELECT 'Oral Agents' AS med_class
  ) AS mc
  LEFT JOIN
    patient_window_flags AS pwf
    ON pc.hadm_id = pwf.hadm_id AND mc.med_class = pwf.med_class
)
SELECT
  fps.med_class,
  COUNT(DISTINCT fps.hadm_id) AS total_cohort_patients,
  SUM(fps.on_early) AS patients_on_in_early_window,
  ROUND(100.0 * SUM(fps.on_early) / COUNT(DISTINCT fps.hadm_id), 1) AS initiation_rate_early_pct,
  SUM(fps.on_late) AS patients_on_in_late_window,
  ROUND(100.0 * SUM(fps.on_late) / COUNT(DISTINCT fps.hadm_id), 1) AS initiation_rate_late_pct,
  COUNTIF(fps.on_early = 1 AND fps.on_late = 1) AS transition_continued,
  COUNTIF(fps.on_early = 0 AND fps.on_late = 1) AS transition_initiated_late,
  COUNTIF(fps.on_early = 1 AND fps.on_late = 0) AS transition_discontinued,
  COUNTIF(fps.on_early = 0 AND fps.on_late = 0) AS transition_never_prescribed
FROM
  full_patient_status AS fps
GROUP BY
  fps.med_class
ORDER BY
  fps.med_class;
