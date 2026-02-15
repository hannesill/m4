WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 79 AND 89
  ),
  pneumonia_admissions AS (
    SELECT
      b.subject_id,
      b.hadm_id,
      b.admittime,
      b.dischtime,
      b.hospital_expire_flag,
      CASE
        WHEN MAX(
          CASE
            WHEN d.icd_code = '5070' OR d.icd_code LIKE 'J69.0%'
              THEN 1
            ELSE 0
          END
        ) = 1
          THEN 'Aspiration Pneumonia'
        WHEN MAX(
          CASE
            WHEN d.icd_code = '486' OR d.icd_code LIKE 'J18%'
              THEN 1
            ELSE 0
          END
        ) = 1
          THEN 'Community-Acquired Pneumonia'
        ELSE NULL
      END AS pneumonia_type
    FROM base_cohort AS b
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON b.hadm_id = d.hadm_id
    WHERE
      (d.icd_version = 9 AND d.icd_code IN ('486', '5070'))
      OR (d.icd_version = 10 AND (d.icd_code LIKE 'J18%' OR d.icd_code LIKE 'J69.0%'))
    GROUP BY
      b.subject_id,
      b.hadm_id,
      b.admittime,
      b.dischtime,
      b.hospital_expire_flag
  ),
  cohort_with_strata AS (
    SELECT
      pa.hadm_id,
      pa.hospital_expire_flag,
      pa.pneumonia_type,
      CASE
        WHEN DATETIME_DIFF(pa.dischtime, pa.admittime, DAY) <= 7
          THEN '<=7 days'
        ELSE '>7 days'
      END AS los_group,
      CASE
        WHEN EXISTS (
          SELECT
            1
          FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
          WHERE
            icu.hadm_id = pa.hadm_id
            AND icu.intime <= DATETIME_ADD(pa.admittime, INTERVAL 24 HOUR)
        )
          THEN 'Day-1 ICU'
        ELSE 'No Day-1 ICU'
      END AS day1_icu_status,
      CAST(EXISTS (
        SELECT
          1
        FROM `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
        WHERE
          proc.hadm_id = pa.hadm_id
          AND (
            (proc.icd_version = 9 AND proc.icd_code IN ('9670', '9671', '9672'))
            OR (proc.icd_version = 10 AND proc.icd_code IN ('5A1935Z', '5A1945Z', '5A1955Z'))
          )
      ) AS INT64) AS has_mech_vent,
      CAST(EXISTS (
        SELECT
          1
        FROM `physionet-data.mimiciv_3_1_icu.inputevents` AS ie
        WHERE
          ie.hadm_id = pa.hadm_id
          AND ie.itemid IN (
            221906,
            221289,
            221749,
            222315,
            221662
          )
      ) AS INT64) AS has_vasopressors,
      CAST(EXISTS (
        SELECT
          1
        FROM `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
        WHERE
          proc.hadm_id = pa.hadm_id
          AND (
            (proc.icd_version = 9 AND proc.icd_code = '3995')
            OR (proc.icd_version = 10 AND proc.icd_code IN ('5A1D00Z', '5A1D60Z'))
          )
      ) AS INT64) AS has_rrt
    FROM pneumonia_admissions AS pa
    WHERE
      pa.pneumonia_type IS NOT NULL
  ),
  strata_template AS (
    SELECT
      pneumonia_type,
      los_group,
      day1_icu_status
    FROM
      (
        SELECT
          pneumonia_type
        FROM UNNEST(['Community-Acquired Pneumonia', 'Aspiration Pneumonia']) AS pneumonia_type
      )
    CROSS JOIN
      (SELECT los_group FROM UNNEST(['<=7 days', '>7 days']) AS los_group)
    CROSS JOIN
      (SELECT day1_icu_status FROM UNNEST(['Day-1 ICU', 'No Day-1 ICU']) AS day1_icu_status)
  )
SELECT
  t.pneumonia_type,
  t.los_group,
  t.day1_icu_status,
  COALESCE(COUNT(c.hadm_id), 0) AS N,
  COALESCE(ROUND(AVG(c.hospital_expire_flag) * 100, 2), 0) AS in_hospital_mortality_rate_pct,
  COALESCE(ROUND(AVG(c.has_mech_vent) * 100, 2), 0) AS mech_vent_prevalence_pct,
  COALESCE(ROUND(AVG(c.has_vasopressors) * 100, 2), 0) AS vasopressor_prevalence_pct,
  COALESCE(ROUND(AVG(c.has_rrt) * 100, 2), 0) AS rrt_prevalence_pct
FROM strata_template AS t
LEFT JOIN cohort_with_strata AS c
  ON t.pneumonia_type = c.pneumonia_type
  AND t.los_group = c.los_group
  AND t.day1_icu_status = c.day1_icu_status
GROUP BY
  t.pneumonia_type,
  t.los_group,
  t.day1_icu_status
ORDER BY
  t.pneumonia_type,
  CASE
    WHEN t.los_group = '<=7 days'
      THEN 1
    ELSE 2
  END,
  CASE
    WHEN t.day1_icu_status = 'Day-1 ICU'
      THEN 1
    ELSE 2
  END;
