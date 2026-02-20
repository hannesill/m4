WITH
  hf_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (
        p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year
      ) BETWEEN 51 AND 61
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            d.icd_code LIKE 'I50%'
            OR d.icd_code LIKE '428%'
          )
      )
  ),
  comorbidity_count AS (
    SELECT
      d.hadm_id,
      COUNT(DISTINCT d.icd_code) AS num_comorbidities
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    WHERE
      d.hadm_id IN (
        SELECT hadm_id FROM hf_cohort
      )
      AND NOT (
        d.icd_code LIKE 'I50%'
        OR d.icd_code LIKE '428%'
      )
    GROUP BY
      d.hadm_id
  ),
  organ_support AS (
    SELECT
      icu.hadm_id,
      MAX(
        CASE
          WHEN pe.itemid IN (225468, 227194, 225477) THEN 1
          ELSE 0
        END
      ) AS has_mv,
      MAX(
        CASE
          WHEN ie.itemid IN (221906, 222315, 221662, 221289, 221749) THEN 1
          ELSE 0
        END
      ) AS has_vaso,
      MAX(
        CASE
          WHEN pe.itemid IN (225802, 225803, 225805, 224270, 225441) THEN 1
          ELSE 0
        END
      ) AS has_rrt
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe ON icu.stay_id = pe.stay_id
      LEFT JOIN `physionet-data.mimiciv_3_1_icu.inputevents` AS ie ON icu.stay_id = ie.stay_id
    WHERE
      icu.hadm_id IN (
        SELECT hadm_id FROM hf_cohort
      )
    GROUP BY
      icu.hadm_id
  ),
  cohort_features AS (
    SELECT
      h.hadm_id,
      h.hospital_expire_flag,
      CASE
        WHEN icu.hadm_id IS NOT NULL THEN 'Higher-Severity (ICU)'
        ELSE 'Lower-Severity (No ICU)'
      END AS severity_level,
      CASE
        WHEN DATETIME_DIFF(h.dischtime, h.admittime, DAY) < 8 THEN '< 8 days'
        ELSE '>= 8 days'
      END AS los_group,
      CASE
        WHEN COALESCE(cc.num_comorbidities, 0) <= 10 THEN 'Low (0-10 comorbidities)'
        WHEN COALESCE(cc.num_comorbidities, 0) <= 20 THEN 'Medium (11-20 comorbidities)'
        ELSE 'High (>20 comorbidities)'
      END AS comorbidity_burden,
      COALESCE(os.has_mv, 0) AS has_mv,
      COALESCE(os.has_vaso, 0) AS has_vaso,
      COALESCE(os.has_rrt, 0) AS has_rrt
    FROM
      hf_cohort AS h
      LEFT JOIN (
        SELECT DISTINCT hadm_id FROM `physionet-data.mimiciv_3_1_icu.icustays`
      ) AS icu ON h.hadm_id = icu.hadm_id
      LEFT JOIN comorbidity_count AS cc ON h.hadm_id = cc.hadm_id
      LEFT JOIN organ_support AS os ON h.hadm_id = os.hadm_id
  ),
  grouped_stats AS (
    SELECT
      severity_level,
      comorbidity_burden,
      los_group,
      COUNT(*) AS total_admissions,
      SUM(hospital_expire_flag) AS total_deaths,
      ROUND(100.0 * AVG(hospital_expire_flag), 2) AS mortality_rate_pct,
      ROUND(100.0 * AVG(has_mv), 2) AS prevalence_mv_pct,
      ROUND(100.0 * AVG(has_vaso), 2) AS prevalence_vaso_pct,
      ROUND(100.0 * AVG(has_rrt), 2) AS prevalence_rrt_pct
    FROM
      cohort_features
    GROUP BY
      severity_level,
      comorbidity_burden,
      los_group
  )
SELECT
  severity_level,
  comorbidity_burden,
  los_group,
  total_admissions,
  total_deaths,
  mortality_rate_pct,
  LAG(mortality_rate_pct, 1, 0) OVER (
    PARTITION BY
      severity_level,
      comorbidity_burden
    ORDER BY
      los_group
  ) AS comparison_mortality_rate_pct,
  CASE
    WHEN los_group = '>= 8 days' THEN ROUND(
      mortality_rate_pct - LAG(mortality_rate_pct, 1, 0) OVER (
        PARTITION BY
          severity_level,
          comorbidity_burden
        ORDER BY
          los_group
      ),
      2
    )
    ELSE NULL
  END AS abs_mortality_diff_vs_short_los,
  CASE
    WHEN
      los_group = '>= 8 days' AND LAG(mortality_rate_pct, 1, 0) OVER (
        PARTITION BY
          severity_level,
          comorbidity_burden
        ORDER BY
          los_group
      ) > 0
      THEN ROUND(
        100.0 * (
          mortality_rate_pct - LAG(mortality_rate_pct, 1, 0) OVER (
            PARTITION BY
              severity_level,
              comorbidity_burden
            ORDER BY
              los_group
          )
        ) / LAG(mortality_rate_pct, 1, 0) OVER (
          PARTITION BY
            severity_level,
            comorbidity_burden
          ORDER BY
            los_group
        ),
        2
      )
    ELSE NULL
  END AS rel_mortality_diff_vs_short_los_pct,
  prevalence_mv_pct,
  prevalence_vaso_pct,
  prevalence_rrt_pct
FROM
  grouped_stats
ORDER BY
  severity_level DESC,
  comorbidity_burden,
  los_group;
