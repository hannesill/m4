WITH
  cohort_hhs AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND icd_code LIKE '250.2%'
      )
      OR (
        icd_version = 10
        AND (
          icd_code LIKE 'E102%'
          OR icd_code LIKE 'E112%'
          OR icd_code LIKE 'E122%'
          OR icd_code LIKE 'E132%'
          OR icd_code LIKE 'E142%'
        )
      )
  ),
  cohort_stays AS (
    SELECT
      p.subject_id,
      i.hadm_id,
      i.stay_id,
      i.intime,
      i.outtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(i.outtime, i.intime, HOUR) / 24.0 AS icu_los_days,
      p.anchor_age + DATETIME_DIFF(
        i.intime,
        DATETIME(p.anchor_year, 1, 1, 0, 0, 0),
        YEAR
      ) AS age_at_icu_admission
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS i
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON i.subject_id = p.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON i.hadm_id = a.hadm_id
    WHERE
      i.hadm_id IN (
        SELECT
          hadm_id
        FROM
          cohort_hhs
      )
      AND p.gender = 'M'
      AND (
        p.anchor_age + DATETIME_DIFF(
          i.intime,
          DATETIME(p.anchor_year, 1, 1, 0, 0, 0),
          YEAR
        )
      ) BETWEEN 78 AND 88
  ),
  vitals_first_24h AS (
    SELECT
      ce.stay_id,
      ce.valuenum,
      CASE
        WHEN ce.itemid = 220045 THEN 'hr'
        WHEN ce.itemid IN (220179, 220050) THEN 'sbp'
        WHEN ce.itemid IN (220181, 220052) THEN 'map'
        WHEN ce.itemid = 220210 THEN 'rr'
        WHEN ce.itemid = 223762 THEN 'tempc'
        WHEN ce.itemid = 220277 THEN 'spo2'
      END AS vital_label
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      INNER JOIN cohort_stays cs ON ce.stay_id = cs.stay_id
    WHERE
      ce.itemid IN (
        220045,
        220179,
        220050,
        220181,
        220052,
        220210,
        223762,
        220277
      )
      AND ce.valuenum IS NOT NULL
      AND ce.charttime BETWEEN cs.intime AND DATETIME_ADD(cs.intime, INTERVAL 24 HOUR)
  ),
  vitals_with_flags AS (
    SELECT
      stay_id,
      vital_label,
      valuenum,
      CASE
        WHEN vital_label = 'hr' AND (valuenum < 60 OR valuenum > 110) THEN 1
        WHEN vital_label = 'sbp' AND (valuenum < 90 OR valuenum > 160) THEN 1
        WHEN vital_label = 'map' AND valuenum < 65 THEN 1
        WHEN vital_label = 'rr' AND (valuenum < 10 OR valuenum > 28) THEN 1
        WHEN vital_label = 'tempc' AND (valuenum < 36.0 OR valuenum > 38.5) THEN 1
        WHEN vital_label = 'spo2' AND valuenum < 92 THEN 1
        ELSE 0
      END AS is_abnormal
    FROM
      vitals_first_24h
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SAFE_DIVIDE(
        STDDEV_SAMP(
          CASE
            WHEN vital_label = 'hr' THEN valuenum
          END
        ),
        AVG(
          CASE
            WHEN vital_label = 'hr' THEN valuenum
          END
        )
      ) AS cv_hr,
      SAFE_DIVIDE(
        STDDEV_SAMP(
          CASE
            WHEN vital_label = 'map' THEN valuenum
          END
        ),
        AVG(
          CASE
            WHEN vital_label = 'map' THEN valuenum
          END
        )
      ) AS cv_map,
      SAFE_DIVIDE(
        STDDEV_SAMP(
          CASE
            WHEN vital_label = 'rr' THEN valuenum
          END
        ),
        AVG(
          CASE
            WHEN vital_label = 'rr' THEN valuenum
          END
        )
      ) AS cv_rr,
      SUM(is_abnormal) AS abnormal_vitals_count
    FROM
      vitals_with_flags
    GROUP BY
      stay_id
  ),
  ranked_patients AS (
    SELECT
      stay_id,
      abnormal_vitals_count,
      (
        COALESCE(cv_hr, 0) + COALESCE(cv_map, 0) + COALESCE(cv_rr, 0)
      ) AS instability_score,
      NTILE(10) OVER (
        ORDER BY
          (
            COALESCE(cv_hr, 0) + COALESCE(cv_map, 0) + COALESCE(cv_rr, 0)
          )
      ) AS instability_decile,
      NTILE(4) OVER (
        ORDER BY
          (
            COALESCE(cv_hr, 0) + COALESCE(cv_map, 0) + COALESCE(cv_rr, 0)
          ) DESC
      ) AS instability_quartile_desc
    FROM
      instability_scores
  )
SELECT
  rp.stay_id,
  cs.subject_id,
  cs.age_at_icu_admission,
  ROUND(rp.instability_score, 4) AS instability_score_cv_sum,
  rp.instability_decile,
  rp.abnormal_vitals_count,
  ROUND(cs.icu_los_days, 2) AS icu_los_days,
  cs.hospital_expire_flag
FROM
  ranked_patients AS rp
  INNER JOIN cohort_stays AS cs ON rp.stay_id = cs.stay_id
WHERE
  rp.instability_quartile_desc = 1
ORDER BY
  instability_score_cv_sum DESC,
  abnormal_vitals_count DESC;
