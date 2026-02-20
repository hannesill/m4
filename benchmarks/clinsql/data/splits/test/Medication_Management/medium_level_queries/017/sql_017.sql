WITH
  patient_cohort AS (
    SELECT DISTINCT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 37 AND 47
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 144
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id AND (
            d.icd_code LIKE 'E08%' OR d.icd_code LIKE 'E09%' OR d.icd_code LIKE 'E10%' OR d.icd_code LIKE 'E11%' OR d.icd_code LIKE 'E13%'
            OR d.icd_code LIKE '250%'
          )
      )
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id AND (
            d.icd_code LIKE 'I50%'
            OR d.icd_code LIKE '428%'
          )
      )
  ),
  medication_events AS (
    SELECT
      pc.hadm_id,
      CASE
        WHEN
          LOWER(rx.drug) LIKE '%insulin%' OR LOWER(rx.drug) LIKE '%metformin%' OR LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%'
          THEN 'Antidiabetic'
        WHEN
          LOWER(rx.drug) LIKE '%metoprolol%' OR LOWER(rx.drug) LIKE '%carvedilol%' OR LOWER(rx.drug) LIKE '%bisoprolol%' OR LOWER(rx.drug) LIKE '%atenolol%' OR LOWER(rx.drug) LIKE '%labetalol%'
          THEN 'Beta-Blocker'
        WHEN
          LOWER(rx.drug) LIKE '%lisinopril%' OR LOWER(rx.drug) LIKE '%enalapril%' OR LOWER(rx.drug) LIKE '%ramipril%' OR LOWER(rx.drug) LIKE '%losartan%' OR LOWER(rx.drug) LIKE '%valsartan%' OR LOWER(rx.drug) LIKE '%irbesartan%' OR LOWER(rx.drug) LIKE '%sacubitril%'
          THEN 'ACEi/ARB/ARNI'
        WHEN
          LOWER(rx.drug) LIKE '%furosemide%' OR LOWER(rx.drug) LIKE '%bumetanide%' OR LOWER(rx.drug) LIKE '%torsemide%'
          THEN 'Loop Diuretic'
        ELSE NULL
      END AS med_class,
      CASE
        WHEN rx.starttime BETWEEN pc.admittime AND DATETIME_ADD(pc.admittime, INTERVAL 72 HOUR)
          THEN 'Early'
        WHEN rx.starttime BETWEEN DATETIME_SUB(pc.dischtime, INTERVAL 72 HOUR) AND pc.dischtime
          THEN 'Final'
        ELSE 'Mid-Stay'
      END AS timing_window
    FROM
      patient_cohort AS pc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON pc.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime BETWEEN pc.admittime AND pc.dischtime
  ),
  patient_med_exposure AS (
    SELECT
      hadm_id,
      med_class,
      MAX(
        CASE
          WHEN timing_window = 'Early'
            THEN 1
          ELSE 0
        END
      ) AS exposed_early,
      MAX(
        CASE
          WHEN timing_window = 'Final'
            THEN 1
          ELSE 0
        END
      ) AS exposed_final
    FROM
      medication_events
    WHERE
      med_class IS NOT NULL
    GROUP BY
      hadm_id,
      med_class
  ),
  cohort_size AS (
    SELECT
      COUNT(DISTINCT hadm_id) AS total_patients
    FROM
      patient_cohort
  )
SELECT
  pme.med_class,
  cs.total_patients AS total_cohort_patients,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(pme.exposed_early = 1) * 100.0,
      cs.total_patients
    ),
    2
  ) AS prevalence_early_pct,
  ROUND(
    SAFE_DIVIDE(
      COUNTIF(pme.exposed_final = 1) * 100.0,
      cs.total_patients
    ),
    2
  ) AS prevalence_final_pct,
  COUNTIF(pme.exposed_early = 1 AND pme.exposed_final = 1) AS count_continued,
  COUNTIF(pme.exposed_early = 0 AND pme.exposed_final = 1) AS count_initiated,
  COUNTIF(pme.exposed_early = 1 AND pme.exposed_final = 0) AS count_discontinued
FROM
  patient_med_exposure AS pme
CROSS JOIN
  cohort_size AS cs
GROUP BY
  pme.med_class,
  cs.total_patients
ORDER BY
  pme.med_class;
