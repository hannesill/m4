WITH
  all_strata AS (
    SELECT
      icu_group,
      los_bucket,
      charlson_bucket,
      los_order
    FROM
      (
        SELECT 'ICU' AS icu_group
        UNION ALL
        SELECT 'Non-ICU' AS icu_group
      ) AS icu_groups
    CROSS JOIN
      (
        SELECT '≤3 days' AS los_bucket, 1 AS los_order
        UNION ALL
        SELECT '4–6 days' AS los_bucket, 2 AS los_order
        UNION ALL
        SELECT '7–10 days' AS los_bucket, 3 AS los_order
        UNION ALL
        SELECT '>10 days' AS los_bucket, 4 AS los_order
      ) AS los_groups
    CROSS JOIN
      (
        SELECT '≤3' AS charlson_bucket
        UNION ALL
        SELECT '4–5' AS charlson_bucket
        UNION ALL
        SELECT '>5' AS charlson_bucket
      ) AS charlson_groups
  ),
  base_admissions AS (
    SELECT DISTINCT
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 39 AND 49
      AND (
        (
          d.icd_version = 9
          AND SUBSTR(d.icd_code, 1, 3) IN ('996', '997', '998', '999')
        )
        OR
        (
          d.icd_version = 10
          AND (
            SUBSTR(d.icd_code, 1, 3) BETWEEN 'T80' AND 'T88'
            OR SUBSTR(d.icd_code, 1, 3) IN ('Y83', 'Y84')
          )
        )
      )
  ),
  cohort_with_features AS (
    SELECT
      b.hadm_id,
      b.hospital_expire_flag,
      CASE WHEN icu.hadm_id IS NOT NULL THEN 'ICU' ELSE 'Non-ICU' END AS icu_group,
      CASE
        WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) <= 3
        THEN '≤3 days'
        WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) BETWEEN 4 AND 6
        THEN '4–6 days'
        WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) BETWEEN 7 AND 10
        THEN '7–10 days'
        WHEN DATETIME_DIFF(b.dischtime, b.admittime, DAY) > 10
        THEN '>10 days'
      END AS los_bucket,
      CASE
        WHEN COALESCE(ch.charlson_comorbidity_index, 0) <= 3
        THEN '≤3'
        WHEN ch.charlson_comorbidity_index BETWEEN 4 AND 5
        THEN '4–5'
        WHEN ch.charlson_comorbidity_index > 5
        THEN '>5'
      END AS charlson_bucket,
      CASE
        WHEN EXISTS (
          SELECT
            1
          FROM
            `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
          WHERE
            pe.hadm_id = b.hadm_id AND pe.itemid IN (225792, 225794, 225790, 225796)
        )
        THEN 1
        ELSE 0
      END AS has_mech_vent,
      CASE
        WHEN EXISTS (
          SELECT
            1
          FROM
            `physionet-data.mimiciv_3_1_icu.inputevents` AS ie
          WHERE
            ie.hadm_id = b.hadm_id
            AND ie.itemid IN (
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
        WHEN EXISTS (
          SELECT
            1
          FROM
            `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
          WHERE
            pe.hadm_id = b.hadm_id
            AND pe.itemid IN (225802, 225803, 225805, 224149, 224145, 225442, 225441, 225809, 225807)
        )
        THEN 1
        ELSE 0
      END AS has_rrt
    FROM
      base_admissions AS b
    LEFT JOIN
      (SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`) AS icu
      ON b.hadm_id = icu.hadm_id
    LEFT JOIN
      `physionet-data.mimiciv_3_1_derived.charlson` AS ch
      ON b.hadm_id = ch.hadm_id
  ),
  grouped_stats AS (
    SELECT
      icu_group,
      los_bucket,
      charlson_bucket,
      COUNT(hadm_id) AS patient_count,
      AVG(hospital_expire_flag) AS mortality_avg,
      AVG(has_mech_vent) AS mech_vent_avg,
      AVG(has_vasopressor) AS vasopressor_avg,
      AVG(has_rrt) AS rrt_avg
    FROM
      cohort_with_features
    WHERE
      los_bucket IS NOT NULL AND charlson_bucket IS NOT NULL
    GROUP BY
      icu_group,
      los_bucket,
      charlson_bucket
  ),
  final_report AS (
    SELECT
      s.icu_group,
      s.los_bucket,
      s.charlson_bucket,
      COALESCE(g.patient_count, 0) AS N,
      ROUND(COALESCE(g.mortality_avg, 0) * 100, 2) AS mortality_rate_pct,
      ROUND(COALESCE(g.mech_vent_avg, 0) * 100, 2) AS mech_vent_prevalence_pct,
      ROUND(COALESCE(g.vasopressor_avg, 0) * 100, 2) AS vasopressor_prevalence_pct,
      ROUND(COALESCE(g.rrt_avg, 0) * 100, 2) AS rrt_prevalence_pct,
      s.los_order
    FROM
      all_strata AS s
    LEFT JOIN
      grouped_stats AS g
      ON s.icu_group = g.icu_group AND s.los_bucket = g.los_bucket AND s.charlson_bucket = g.charlson_bucket
  )
SELECT
  icu_group,
  los_bucket,
  charlson_bucket,
  N,
  mortality_rate_pct,
  ROUND(
    mortality_rate_pct - FIRST_VALUE(mortality_rate_pct) OVER (PARTITION BY icu_group, charlson_bucket ORDER BY los_order),
    2
  ) AS absolute_mortality_difference,
  ROUND(
    SAFE_DIVIDE(
      mortality_rate_pct - FIRST_VALUE(mortality_rate_pct) OVER (PARTITION BY icu_group, charlson_bucket ORDER BY los_order),
      FIRST_VALUE(mortality_rate_pct) OVER (PARTITION BY icu_group, charlson_bucket ORDER BY los_order)
    ) * 100,
    2
  ) AS relative_mortality_difference_pct,
  mech_vent_prevalence_pct,
  vasopressor_prevalence_pct,
  rrt_prevalence_pct
FROM
  final_report
ORDER BY
  icu_group DESC,
  charlson_bucket,
  los_order;
