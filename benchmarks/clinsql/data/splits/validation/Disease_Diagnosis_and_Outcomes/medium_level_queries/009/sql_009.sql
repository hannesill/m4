WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 53 AND 63
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
  ),
  sepsis_admissions AS (
    SELECT
      bc.subject_id,
      bc.hadm_id,
      bc.admittime,
      bc.dischtime,
      bc.hospital_expire_flag
    FROM
      base_cohort AS bc
    WHERE
      EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = bc.hadm_id
          AND (
            d.icd_code = '99591'
            OR d.icd_code LIKE 'A41%'
          )
      )
      AND NOT EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = bc.hadm_id
          AND (
            d.icd_code = '78552'
            OR d.icd_code = 'R6521'
            OR d.icd_code LIKE 'T8112%'
          )
      )
  ),
  organ_support_flags AS (
    SELECT
      sa.hadm_id,
      MAX(
        CASE
          WHEN pe.itemid IN (
            225792,
            225794
          )
          THEN 1
          ELSE 0
        END
      ) AS has_mech_vent,
      MAX(
        CASE
          WHEN ie.itemid IN (
            221906,
            221289,
            222315,
            221662,
            221749,
            221653
          )
          THEN 1
          ELSE 0
        END
      ) AS has_vasopressor,
      MAX(
        CASE
          WHEN pe.itemid IN (
            225802,
            225803,
            225805,
            225807
          )
          THEN 1
          ELSE 0
        END
      ) AS has_rrt
    FROM
      sepsis_admissions AS sa
    LEFT JOIN
      `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
      ON sa.hadm_id = pe.hadm_id
    LEFT JOIN
      `physionet-data.mimiciv_3_1_icu.inputevents` AS ie
      ON sa.hadm_id = ie.hadm_id
    GROUP BY
      sa.hadm_id
  ),
  final_cohort AS (
    SELECT
      sa.hadm_id,
      sa.hospital_expire_flag,
      CASE
        WHEN DATETIME_DIFF(sa.dischtime, sa.admittime, DAY) < 8
        THEN '<8 days'
        ELSE '>=8 days'
      END AS los_category,
      CASE
        WHEN EXISTS (
          SELECT
            1
          FROM
            `physionet-data.mimiciv_3_1_icu.icustays` AS icu
          WHERE
            icu.hadm_id = sa.hadm_id
            AND DATETIME_DIFF(icu.intime, sa.admittime, HOUR) <= 24
        )
        THEN 'Day-1 ICU'
        ELSE 'Non-ICU on Day-1'
      END AS day1_icu_category,
      COALESCE(osf.has_mech_vent, 0) AS has_mech_vent,
      COALESCE(osf.has_vasopressor, 0) AS has_vasopressor,
      COALESCE(osf.has_rrt, 0) AS has_rrt
    FROM
      sepsis_admissions AS sa
    LEFT JOIN
      organ_support_flags AS osf
      ON sa.hadm_id = osf.hadm_id
  )
SELECT
  los_category,
  day1_icu_category,
  COUNT(*) AS total_admissions,
  SUM(hospital_expire_flag) AS in_hospital_deaths,
  ROUND(AVG(hospital_expire_flag) * 100.0, 2) AS mortality_rate_percent,
  ROUND(AVG(has_mech_vent) * 100.0, 2) AS mech_vent_prevalence_percent,
  ROUND(AVG(has_vasopressor) * 100.0, 2) AS vasopressor_prevalence_percent,
  ROUND(AVG(has_rrt) * 100.0, 2) AS rrt_prevalence_percent
FROM
  final_cohort
GROUP BY
  los_category,
  day1_icu_category
ORDER BY
  los_category,
  day1_icu_category;
