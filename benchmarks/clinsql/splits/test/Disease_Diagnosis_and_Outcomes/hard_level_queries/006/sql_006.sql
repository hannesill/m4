WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      p.dod,
      a.admittime,
      a.dischtime,
      (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 70 AND 80
  ),
  gi_bleed_admissions AS (
    SELECT
      bc.subject_id,
      bc.hadm_id,
      bc.dod,
      bc.admittime,
      bc.dischtime
    FROM
      base_cohort AS bc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON bc.hadm_id = d.hadm_id
    WHERE
      (d.icd_version = 9 AND d.icd_code IN ('5781'))
      OR (d.icd_version = 10 AND d.icd_code IN ('K921', 'K922'))
    GROUP BY
      bc.subject_id,
      bc.hadm_id,
      bc.dod,
      bc.admittime,
      bc.dischtime
  ),
  complications_and_outcomes AS (
    SELECT
      ga.hadm_id,
      DATETIME_DIFF(ga.dischtime, ga.admittime, DAY) AS los_days,
      CASE
        WHEN ga.dod IS NOT NULL AND DATETIME_DIFF(ga.dod, ga.dischtime, DAY) BETWEEN 0 AND 90
        THEN 1
        ELSE 0
      END AS is_90_day_mortality,
      MAX(CASE
        WHEN (d.icd_version = 10 AND d.icd_code IN ('R6881', 'R570')) OR (d.icd_version = 9 AND d.icd_code IN ('99592', '78552'))
        THEN 1 ELSE 0
      END) AS has_multi_organ_failure,
      MAX(CASE
        WHEN (d.icd_version = 10 AND d.icd_code IN ('R6521', 'A419')) OR (d.icd_version = 9 AND d.icd_code IN ('99592', '0389'))
        THEN 1 ELSE 0
      END) AS has_septic_shock,
      MAX(CASE
        WHEN (d.icd_version = 10 AND (d.icd_code LIKE 'I21%' OR d.icd_code = 'I469')) OR (d.icd_version = 9 AND (d.icd_code LIKE '410%' OR d.icd_code = '4275'))
        THEN 1 ELSE 0
      END) AS has_mi_complication,
      MAX(CASE
        WHEN (d.icd_version = 10 AND d.icd_code IN ('J9600', 'J80')) OR (d.icd_version = 9 AND d.icd_code IN ('51881', '51882'))
        THEN 1 ELSE 0
      END) AS has_respiratory_failure
    FROM
      gi_bleed_admissions AS ga
    LEFT JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON ga.hadm_id = d.hadm_id
    GROUP BY
      ga.hadm_id,
      ga.dischtime,
      ga.admittime,
      ga.dod
  ),
  ranked_admissions AS (
    SELECT
      co.*,
      GREATEST(co.has_multi_organ_failure, co.has_septic_shock, co.has_mi_complication, co.has_respiratory_failure) AS has_major_complication,
      NTILE(5) OVER (
        ORDER BY
          (
            (co.has_multi_organ_failure * 20)
            + (co.has_septic_shock * 20)
            + (co.has_mi_complication * 15)
            + (co.has_respiratory_failure * 15)
          ) ASC
      ) AS risk_quintile
    FROM
      complications_and_outcomes AS co
  )
SELECT
  ra.risk_quintile,
  COUNT(ra.hadm_id) AS num_patients,
  ROUND(AVG(ra.is_90_day_mortality), 4) AS ninety_day_mortality_rate,
  ROUND(AVG(ra.has_major_complication), 4) AS major_complication_rate,
  APPROX_QUANTILES(
    CASE WHEN ra.is_90_day_mortality = 0 THEN ra.los_days END, 100
  )[OFFSET(50)] AS median_survivor_los_days
FROM
  ranked_admissions AS ra
GROUP BY
  ra.risk_quintile
ORDER BY
  ra.risk_quintile;
