WITH
  cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 60 AND 70
      AND a.dischtime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, HOUR) >= 48
    GROUP BY
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime
    HAVING
      SUM(CASE WHEN d.icd_code LIKE 'E11%' OR d.icd_code LIKE '250%' THEN 1 ELSE 0 END) > 0
      AND SUM(CASE WHEN d.icd_code LIKE 'I50%' OR d.icd_code LIKE '428%' THEN 1 ELSE 0 END) > 0
  ),
  cohort_total AS (
    SELECT COUNT(DISTINCT hadm_id) AS total_admissions FROM cohort
  ),
  medication_events AS (
    SELECT
      c.hadm_id,
      CASE
        WHEN LOWER(rx.drug) LIKE '%insulin%' OR LOWER(rx.drug) LIKE '%metformin%' OR LOWER(rx.drug) LIKE '%glipizide%' OR LOWER(rx.drug) LIKE '%glyburide%' OR LOWER(rx.drug) LIKE '%sitagliptin%' OR LOWER(rx.drug) LIKE '%linagliptin%' THEN 'Antidiabetic'
        WHEN LOWER(rx.drug) LIKE '%metoprolol%' OR LOWER(rx.drug) LIKE '%carvedilol%' OR LOWER(rx.drug) LIKE '%bisoprolol%' OR LOWER(rx.drug) LIKE '%atenolol%' OR LOWER(rx.drug) LIKE '%labetalol%' THEN 'Beta-blocker'
        WHEN LOWER(rx.drug) LIKE '%lisinopril%' OR LOWER(rx.drug) LIKE '%enalapril%' OR LOWER(rx.drug) LIKE '%ramipril%' OR LOWER(rx.drug) LIKE '%losartan%' OR LOWER(rx.drug) LIKE '%valsartan%' OR LOWER(rx.drug) LIKE '%irbesartan%' OR LOWER(rx.drug) LIKE '%sacubitril%' THEN 'ACEi/ARB/ARNI'
        WHEN LOWER(rx.drug) LIKE '%furosemide%' OR LOWER(rx.drug) LIKE '%bumetanide%' OR LOWER(rx.drug) LIKE '%torsemide%' THEN 'Loop Diuretic'
        ELSE NULL
      END AS med_class,
      CASE WHEN DATETIME_DIFF(rx.starttime, c.admittime, HOUR) <= 48 THEN 1 ELSE 0 END AS in_first_48h,
      CASE WHEN DATETIME_DIFF(c.dischtime, rx.starttime, HOUR) <= 24 THEN 1 ELSE 0 END AS in_final_24h
    FROM
      cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      ON c.hadm_id = rx.hadm_id
    WHERE
      rx.starttime IS NOT NULL
      AND rx.starttime >= c.admittime
      AND rx.starttime <= c.dischtime
  ),
  initiation_counts AS (
    SELECT
      med_class,
      COUNT(DISTINCT CASE WHEN in_first_48h = 1 THEN hadm_id END) AS n_initiated_first_48h,
      COUNT(DISTINCT CASE WHEN in_final_24h = 1 THEN hadm_id END) AS n_initiated_final_24h
    FROM
      medication_events
    WHERE
      med_class IS NOT NULL
    GROUP BY
      med_class
  )
SELECT
  ic.med_class,
  ct.total_admissions,
  ic.n_initiated_first_48h,
  ROUND(ic.n_initiated_first_48h * 100.0 / ct.total_admissions, 2) AS pct_initiated_first_48h,
  ic.n_initiated_final_24h,
  ROUND(ic.n_initiated_final_24h * 100.0 / ct.total_admissions, 2) AS pct_initiated_final_24h,
  ROUND(
    (ic.n_initiated_first_48h * 100.0 / ct.total_admissions) - (ic.n_initiated_final_24h * 100.0 / ct.total_admissions),
    2
  ) AS absolute_difference_pp
FROM
  initiation_counts AS ic
CROSS JOIN
  cohort_total AS ct
ORDER BY
  ic.med_class;
