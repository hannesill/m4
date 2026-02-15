WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) AS age_at_admission,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS length_of_stay
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year
      ) BETWEEN 44 AND 54
      AND a.dischtime IS NOT NULL
      AND a.admittime IS NOT NULL
      AND DATETIME_DIFF(a.dischtime, a.admittime, DAY) >= 0
  ),
  stroke_cohort AS (
    SELECT
      b.hadm_id,
      b.subject_id,
      b.hospital_expire_flag,
      b.length_of_stay,
      CASE
        WHEN SUM(
          CASE
            WHEN d.icd_version = 9 AND d.icd_code IN ('430', '431') THEN 1
            WHEN d.icd_version = 9 AND d.icd_code LIKE '432%' THEN 1
            WHEN d.icd_version = 10 AND d.icd_code LIKE 'I60%' THEN 1
            WHEN d.icd_version = 10 AND d.icd_code LIKE 'I61%' THEN 1
            WHEN d.icd_version = 10 AND d.icd_code LIKE 'I62%' THEN 1
            ELSE 0
          END
        ) > 0 THEN 'Hemorrhagic'
        WHEN SUM(
          CASE
            WHEN d.icd_version = 9 AND d.icd_code LIKE '433%' THEN 1
            WHEN d.icd_version = 9 AND d.icd_code LIKE '434%' THEN 1
            WHEN d.icd_version = 9 AND d.icd_code = '436' THEN 1
            WHEN d.icd_version = 10 AND d.icd_code LIKE 'I63%' THEN 1
            ELSE 0
          END
        ) > 0 THEN 'Ischemic'
        ELSE 'Other'
      END AS stroke_type
    FROM
      base_admissions AS b
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON b.hadm_id = d.hadm_id
    GROUP BY
      b.hadm_id,
      b.subject_id,
      b.hospital_expire_flag,
      b.length_of_stay
    HAVING
      stroke_type IN ('Ischemic', 'Hemorrhagic')
  ),
  comorbidity_count AS (
    SELECT
      s.hadm_id,
      COUNT(
        DISTINCT CASE
          WHEN (
            d.icd_version = 9
            AND d.icd_code NOT IN ('430', '431', '436')
            AND d.icd_code NOT LIKE '432%'
            AND d.icd_code NOT LIKE '433%'
            AND d.icd_code NOT LIKE '434%'
          )
          OR (
            d.icd_version = 10
            AND d.icd_code NOT LIKE 'I60%'
            AND d.icd_code NOT LIKE 'I61%'
            AND d.icd_code NOT LIKE 'I62%'
            AND d.icd_code NOT LIKE 'I63%'
          ) THEN d.icd_code
          ELSE NULL
        END
      ) AS num_comorbidities
    FROM
      stroke_cohort AS s
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON s.hadm_id = d.hadm_id
    GROUP BY
      s.hadm_id
  ),
  organ_support_flags AS (
    SELECT
      s.hadm_id,
      MAX(
        CASE
          WHEN proc.itemid IN (
            225792,
            225794
          ) THEN 1
          ELSE 0
        END
      ) AS has_mech_vent,
      MAX(
        CASE
          WHEN inp.itemid IN (
            221906,
            221289,
            222315,
            221662,
            221749
          ) THEN 1
          ELSE 0
        END
      ) AS has_vasopressors,
      MAX(
        CASE
          WHEN proc.itemid IN (
            225802,
            225803,
            225805,
            224149,
            224144
          ) THEN 1
          ELSE 0
        END
      ) AS has_rrt
    FROM
      stroke_cohort AS s
      LEFT JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu ON s.hadm_id = icu.hadm_id
      LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS proc ON icu.stay_id = proc.stay_id
      LEFT JOIN `physionet-data.mimiciv_3_1_icu.inputevents` AS inp ON icu.stay_id = inp.stay_id
    GROUP BY
      s.hadm_id
  ),
  final_data AS (
    SELECT
      s.hadm_id,
      s.hospital_expire_flag,
      s.length_of_stay,
      s.stroke_type,
      CASE
        WHEN s.length_of_stay <= 5 THEN '≤5 days'
        ELSE '>5 days'
      END AS los_category,
      CASE
        WHEN c.num_comorbidities <= 2 THEN 'Low (0-2)'
        WHEN c.num_comorbidities BETWEEN 3 AND 5 THEN 'Medium (3-5)'
        ELSE 'High (>5)'
      END AS comorbidity_burden,
      COALESCE(os.has_mech_vent, 0) AS has_mech_vent,
      COALESCE(os.has_vasopressors, 0) AS has_vasopressors,
      COALESCE(os.has_rrt, 0) AS has_rrt
    FROM
      stroke_cohort AS s
      INNER JOIN comorbidity_count AS c ON s.hadm_id = c.hadm_id
      LEFT JOIN organ_support_flags AS os ON s.hadm_id = os.hadm_id
  )
SELECT
  stroke_type,
  los_category,
  comorbidity_burden,
  COUNT(hadm_id) AS total_admissions,
  SUM(hospital_expire_flag) AS total_deaths,
  ROUND(
    SAFE_DIVIDE(SUM(hospital_expire_flag) * 100.0, COUNT(hadm_id)),
    2
  ) AS mortality_rate_pct,
  APPROX_QUANTILES(length_of_stay, 100)[OFFSET(50)] AS median_los_days,
  ROUND(
    SAFE_DIVIDE(SUM(has_mech_vent) * 100.0, COUNT(hadm_id)),
    1
  ) AS mech_vent_prevalence_pct,
  ROUND(
    SAFE_DIVIDE(SUM(has_vasopressors) * 100.0, COUNT(hadm_id)),
    1
  ) AS vasopressor_prevalence_pct,
  ROUND(
    SAFE_DIVIDE(SUM(has_rrt) * 100.0, COUNT(hadm_id)),
    1
  ) AS rrt_prevalence_pct
FROM
  final_data
GROUP BY
  stroke_type,
  los_category,
  comorbidity_burden
ORDER BY
  stroke_type,
  CASE
    WHEN comorbidity_burden = 'Low (0-2)' THEN 1
    WHEN comorbidity_burden = 'Medium (3-5)' THEN 2
    ELSE 3
  END,
  los_category;
