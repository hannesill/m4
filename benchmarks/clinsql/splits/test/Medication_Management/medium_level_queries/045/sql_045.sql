WITH
  cohort AS (
    SELECT DISTINCT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_diabetes
      ON a.hadm_id = d_diabetes.hadm_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_hf
      ON a.hadm_id = d_hf.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 54 AND 64
      AND (
        d_diabetes.icd_code LIKE 'E10%' OR d_diabetes.icd_code LIKE 'E11%' OR d_diabetes.icd_code LIKE '250%'
      )
      AND (
        d_hf.icd_code LIKE 'I50%' OR d_hf.icd_code LIKE '428%'
      )
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
  ),
  total_cohort_count AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_patients
    FROM
      cohort
  ),
  medication_events AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%'
        THEN 'Insulin'
        WHEN
          LOWER(rx.drug) LIKE '%metformin%'
          OR LOWER(rx.drug) LIKE '%glipizide%'
          OR LOWER(rx.drug) LIKE '%glyburide%'
          OR LOWER(rx.drug) LIKE '%sitagliptin%'
          OR LOWER(rx.drug) LIKE '%linagliptin%'
        THEN 'Oral Agent'
        ELSE NULL
      END AS medication_class,
      CASE
        WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) BETWEEN 0 AND 12
        THEN 'Early_12hr'
        WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) BETWEEN 0 AND 48
        THEN 'Discharge_48hr'
        ELSE NULL
      END AS period
    FROM
      cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
  ),
  patient_counts_by_period AS (
    SELECT
      medication_class,
      period,
      COUNT(DISTINCT hadm_id) AS patient_count
    FROM
      medication_events
    WHERE
      medication_class IS NOT NULL AND period IS NOT NULL
    GROUP BY
      medication_class,
      period
  )
SELECT
  pc.medication_class,
  SUM(
    CASE WHEN pc.period = 'Early_12hr' THEN pc.patient_count ELSE 0 END
  ) AS patients_in_early_period,
  SUM(
    CASE WHEN pc.period = 'Discharge_48hr' THEN pc.patient_count ELSE 0 END
  ) AS patients_in_discharge_period,
  ROUND(
    (
      SUM(CASE WHEN pc.period = 'Early_12hr' THEN pc.patient_count ELSE 0 END) * 100.0
    ) / tcc.total_patients,
    2
  ) AS prevalence_early_pct,
  ROUND(
    (
      SUM(CASE WHEN pc.period = 'Discharge_48hr' THEN pc.patient_count ELSE 0 END) * 100.0
    ) / tcc.total_patients,
    2
  ) AS prevalence_discharge_pct,
  (
    ROUND(
      (
        SUM(CASE WHEN pc.period = 'Discharge_48hr' THEN pc.patient_count ELSE 0 END) * 100.0
      ) / tcc.total_patients,
      2
    ) - ROUND(
      (
        SUM(CASE WHEN pc.period = 'Early_12hr' THEN pc.patient_count ELSE 0 END) * 100.0
      ) / tcc.total_patients,
      2
    )
  ) AS net_change_pp,
  tcc.total_patients AS total_cohort_patients
FROM
  patient_counts_by_period AS pc
CROSS JOIN
  total_cohort_count AS tcc
GROUP BY
  pc.medication_class,
  tcc.total_patients
ORDER BY
  pc.medication_class;
