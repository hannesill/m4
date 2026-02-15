WITH
  base_cohort AS (
    SELECT
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 71 AND 81
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '996' AND '999')
            OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 3) BETWEEN 'T80' AND 'T88')
          )
      )
  ),
  cohort_features AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
      CASE WHEN icu.hadm_id IS NOT NULL THEN 'ICU' ELSE 'Non-ICU' END AS icu_status,
      icu.stay_ids
    FROM base_cohort AS c
    LEFT JOIN (
      SELECT
        hadm_id,
        ARRAY_AGG(stay_id) AS stay_ids
      FROM `physionet-data.mimiciv_3_1_icu.icustays`
      GROUP BY
        hadm_id
    ) AS icu
      ON c.hadm_id = icu.hadm_id
  ),
  organ_support AS (
    SELECT
      cf.hadm_id,
      cf.hospital_expire_flag,
      cf.los_days,
      cf.icu_status,
      CASE
        WHEN
          cf.icu_status = 'ICU' AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_icu.procedureevents`
            WHERE
              stay_id IN UNNEST(cf.stay_ids) AND itemid IN (225792, 225794)
          )
          THEN 1
        ELSE 0
      END AS has_mech_vent,
      CASE
        WHEN
          cf.icu_status = 'ICU' AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_icu.inputevents`
            WHERE
              stay_id IN UNNEST(cf.stay_ids)
              AND itemid IN (
                221906,
                221289,
                221749,
                222315,
                221662
              )
          )
          THEN 1
        ELSE 0
      END AS has_vasopressor,
      CASE
        WHEN
          cf.icu_status = 'ICU' AND EXISTS (
            SELECT 1
            FROM `physionet-data.mimiciv_3_1_icu.procedureevents`
            WHERE
              stay_id IN UNNEST(cf.stay_ids)
              AND itemid IN (
                225802,
                225803,
                225805,
                225441
              )
          )
          THEN 1
        ELSE 0
      END AS has_rrt
    FROM cohort_features AS cf
    WHERE
      cf.los_days > 0
  ),
  los_quartiles AS (
    SELECT
      os.*,
      NTILE(4) OVER (PARTITION BY os.icu_status ORDER BY os.los_days) AS los_quartile
    FROM organ_support AS os
  ),
  grouped_stats AS (
    SELECT
      icu_status,
      los_quartile,
      COUNT(DISTINCT hadm_id) AS n,
      MIN(los_days) AS min_los,
      MAX(los_days) AS max_los,
      AVG(hospital_expire_flag) AS mortality_rate_raw,
      AVG(has_mech_vent) AS mech_vent_prevalence_raw,
      AVG(has_vasopressor) AS vasopressor_prevalence_raw,
      AVG(has_rrt) AS rrt_prevalence_raw
    FROM los_quartiles
    GROUP BY
      icu_status,
      los_quartile
  ),
  final_data_scaffold AS (
    SELECT
      s.icu_status,
      s.los_quartile,
      COALESCE(g.n, 0) AS n,
      g.min_los,
      g.max_los,
      COALESCE(g.mortality_rate_raw, 0) AS mortality_rate_raw,
      COALESCE(g.mech_vent_prevalence_raw, 0) AS mech_vent_prevalence_raw,
      COALESCE(g.vasopressor_prevalence_raw, 0) AS vasopressor_prevalence_raw,
      COALESCE(g.rrt_prevalence_raw, 0) AS rrt_prevalence_raw
    FROM (
      SELECT
        icu_status,
        los_quartile
      FROM
        (SELECT 'ICU' AS icu_status UNION ALL SELECT 'Non-ICU')
        CROSS JOIN (SELECT q AS los_quartile FROM UNNEST(GENERATE_ARRAY(1, 4)) AS q)
    ) AS s
    LEFT JOIN grouped_stats AS g
      ON s.icu_status = g.icu_status AND s.los_quartile = g.los_quartile
  ),
  final_comparison AS (
    SELECT
      *,
      FIRST_VALUE(
        CASE WHEN n > 0 THEN mortality_rate_raw ELSE NULL END IGNORE NULLS
      ) OVER (PARTITION BY icu_status ORDER BY los_quartile) AS baseline_mortality_q1
    FROM final_data_scaffold
  )
SELECT
  fc.icu_status,
  CASE
    WHEN fc.n = 0
      THEN CONCAT('Q', fc.los_quartile, ' (no patients)')
    ELSE CONCAT('Q', fc.los_quartile, ' (', fc.min_los, '-', fc.max_los, ' days)')
  END AS los_quartile_range,
  fc.n,
  ROUND(fc.mortality_rate_raw * 100, 2) AS in_hospital_mortality_rate_pct,
  CASE
    WHEN
      fc.los_quartile > 1 AND fc.n > 0 AND fc.baseline_mortality_q1 IS NOT NULL
      THEN ROUND((fc.mortality_rate_raw - fc.baseline_mortality_q1) * 100, 2)
    ELSE NULL
  END AS abs_mortality_diff_from_q1_pct_points,
  CASE
    WHEN
      fc.los_quartile > 1 AND fc.n > 0 AND fc.baseline_mortality_q1 IS NOT NULL
      THEN ROUND(
        SAFE_DIVIDE(fc.mortality_rate_raw - fc.baseline_mortality_q1, fc.baseline_mortality_q1)
        * 100,
        2
      )
    ELSE NULL
  END AS rel_mortality_diff_from_q1_pct,
  ROUND(fc.mech_vent_prevalence_raw * 100, 2) AS mech_vent_prevalence_pct,
  ROUND(fc.vasopressor_prevalence_raw * 100, 2) AS vasopressor_prevalence_pct,
  ROUND(fc.rrt_prevalence_raw * 100, 2) AS rrt_prevalence_pct
FROM final_comparison AS fc
ORDER BY
  fc.icu_status DESC,
  fc.los_quartile;
