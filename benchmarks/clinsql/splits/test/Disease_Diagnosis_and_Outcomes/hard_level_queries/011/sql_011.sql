WITH
  patient_base AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      p.gender,
      a.admittime,
      a.dischtime,
      a.deathtime,
      (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)) BETWEEN 88 AND 98
  ),
  ami_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND icd_code LIKE '410%')
      OR (icd_version = 10 AND icd_code LIKE 'I21%')
  ),
  icu_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays`
  ),
  comorbidity_and_critical_diags AS (
    SELECT
      hadm_id,
      MAX(CASE
        WHEN (icd_version = 9 AND icd_code LIKE '584%') OR (icd_version = 10 AND icd_code LIKE 'N17%')
        THEN 1
        ELSE 0
      END) AS has_aki,
      MAX(CASE
        WHEN (icd_version = 9 AND icd_code IN ('518.82', '518.5')) OR (icd_version = 10 AND icd_code = 'J80')
        THEN 1
        ELSE 0
      END) AS has_ards,
      COUNT(DISTINCT CASE
        WHEN
          (icd_version = 10 AND icd_code IN ('R68.81', 'R57.0', 'R65.21', 'A41.9', 'I46.9', 'J96.00', 'J80', 'Z51.11', 'R06.03'))
          OR (icd_version = 10 AND icd_code LIKE 'I21%')
          OR (icd_version = 9 AND icd_code IN ('995.92', '785.52', '038.9', '427.5', '518.81', '518.82', 'V58.11', '786.03'))
          OR (icd_version = 9 AND icd_code LIKE '410%')
        THEN icd_code
      END) AS critical_diag_count
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  final_cohort_data AS (
    SELECT
      pb.subject_id,
      pb.hadm_id,
      pb.age_at_admission,
      pb.admittime,
      pb.dischtime,
      pb.deathtime,
      COALESCE(com.has_aki, 0) AS has_aki,
      COALESCE(com.has_ards, 0) AS has_ards,
      COALESCE(com.critical_diag_count, 0) AS critical_diag_count,
      CASE
        WHEN pb.deathtime IS NOT NULL THEN DATETIME_DIFF(pb.deathtime, pb.admittime, DAY)
        ELSE NULL
      END AS survival_days_if_deceased,
      CASE
        WHEN pb.deathtime IS NOT NULL AND DATETIME_DIFF(pb.deathtime, pb.admittime, DAY) <= 30 THEN 1
        ELSE 0
      END AS died_within_30_days,
      COALESCE(DATETIME_DIFF(pb.dischtime, pb.admittime, DAY), 0) AS length_of_stay
    FROM
      patient_base AS pb
    INNER JOIN
      ami_admissions AS ami ON pb.hadm_id = ami.hadm_id
    INNER JOIN
      icu_admissions AS icu ON pb.hadm_id = icu.hadm_id
    LEFT JOIN
      comorbidity_and_critical_diags AS com ON pb.hadm_id = com.hadm_id
  ),
  cohort_with_scores AS (
    SELECT
      *,
      LEAST(100,
        (age_at_admission - 88) * 4
        + (LEAST(length_of_stay, 20) * 1.5)
        + (LEAST(critical_diag_count, 10) * 3)
        + ((has_aki + has_ards) * 10)
      ) AS composite_risk_score,
      PERCENT_RANK() OVER (ORDER BY
        LEAST(100,
          (age_at_admission - 88) * 4
          + (LEAST(length_of_stay, 20) * 1.5)
          + (LEAST(critical_diag_count, 10) * 3)
          + ((has_aki + has_ards) * 10)
        ) ASC
      ) AS percentile_rank_of_risk_score
    FROM
      final_cohort_data
  )
SELECT
  ROUND(AVG(CASE WHEN age_at_admission = 93 THEN percentile_rank_of_risk_score ELSE NULL END) * 100, 2) AS avg_percentile_rank_for_93_yo,
  ROUND(AVG(died_within_30_days) * 100, 2) AS mortality_rate_30_day_pct,
  ROUND(AVG(has_aki) * 100, 2) AS aki_rate_pct,
  ROUND(AVG(has_ards) * 100, 2) AS ards_rate_pct,
  APPROX_QUANTILES(survival_days_if_deceased, 2)[OFFSET(1)] AS median_survival_days_for_deceased,
  COUNT(*) AS total_patients_in_cohort
FROM
  cohort_with_scores;
