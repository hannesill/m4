WITH
  cohort AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 49 AND 59
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 72
      AND a.hadm_id IN (
        SELECT hadm_id FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          icd_code LIKE 'E11%' OR (icd_version = 9 AND icd_code LIKE '250%')
        INTERSECT DISTINCT
        SELECT hadm_id FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          icd_code LIKE 'I50%' OR (icd_version = 9 AND icd_code LIKE '428%')
      )
  ),
  medication_periods AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' OR LOWER(rx.drug) LIKE '%metformin%' OR LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%'
          THEN 'Antidiabetic'
        WHEN LOWER(rx.drug) LIKE '%metoprolol%' OR LOWER(rx.drug) LIKE '%carvedilol%' OR LOWER(rx.drug) LIKE '%bisoprolol%'
          THEN 'Beta-Blocker'
        WHEN LOWER(rx.drug) LIKE '%lisinopril%' OR LOWER(rx.drug) LIKE '%enalapril%' OR LOWER(rx.drug) LIKE '%ramipril%'
             OR LOWER(rx.drug) LIKE '%losartan%' OR LOWER(rx.drug) LIKE '%valsartan%' OR LOWER(rx.drug) LIKE '%irbesartan%'
             OR LOWER(rx.drug) LIKE '%sacubitril%'
          THEN 'ACEi/ARB/ARNI'
        WHEN LOWER(rx.drug) LIKE '%furosemide%' OR LOWER(rx.drug) LIKE '%bumetanide%' OR LOWER(rx.drug) LIKE '%torsemide%'
          THEN 'Loop Diuretic'
        ELSE NULL
      END AS med_class,
      (DATETIME_DIFF(rx.starttime, c.admittime, HOUR) <= 24) AS on_early,
      (DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 48) AS on_late
    FROM
      cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN c.admittime AND c.dischtime
  ),
  patient_class_exposure AS (
    SELECT
      hadm_id,
      med_class,
      LOGICAL_OR(on_early) AS was_on_early,
      LOGICAL_OR(on_late) AS was_on_late
    FROM
      medication_periods
    WHERE
      med_class IS NOT NULL
      AND (on_early OR on_late)
    GROUP BY
      hadm_id,
      med_class
  )
SELECT
  pce.med_class,
  cohort_count.total_patients AS total_cohort_patients,
  COUNTIF(pce.was_on_early) AS patients_on_early,
  ROUND(COUNTIF(pce.was_on_early) * 100.0 / cohort_count.total_patients, 1) AS prevalence_early_pct,
  COUNTIF(pce.was_on_late) AS patients_on_late,
  ROUND(COUNTIF(pce.was_on_late) * 100.0 / cohort_count.total_patients, 1) AS prevalence_late_pct,
  COUNTIF(pce.was_on_early AND pce.was_on_late) AS transition_continued,
  COUNTIF(NOT pce.was_on_early AND pce.was_on_late) AS transition_initiated,
  COUNTIF(pce.was_on_early AND NOT pce.was_on_late) AS transition_discontinued
FROM
  patient_class_exposure AS pce
CROSS JOIN
  (SELECT COUNT(DISTINCT hadm_id) AS total_patients FROM cohort) AS cohort_count
GROUP BY
  pce.med_class,
  cohort_count.total_patients
ORDER BY
  pce.med_class;
