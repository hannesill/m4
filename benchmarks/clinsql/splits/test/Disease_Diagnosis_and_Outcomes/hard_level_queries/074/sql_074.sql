WITH
  admissions_base AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      pat.gender,
      (EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age AS age_at_admission,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      pat.dod
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
        ON pat.subject_id = adm.subject_id
    WHERE
      pat.gender = 'M'
      AND ((EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) + pat.anchor_age) BETWEEN 79 AND 89
  ),
  diagnoses_agg AS (
    SELECT
      hadm_id,
      MAX(
        CASE
          WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 5) IN ('41511', '41513', '41519'))
            OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I26')
          THEN 1
          ELSE 0
        END
      ) AS has_pe,
      COUNT(DISTINCT icd_code) AS diagnosis_count,
      COUNT(
        DISTINCT CASE
          WHEN
            (
              icd_version = 10 AND icd_code IN (
                'R68.81', 'R57.0', 'R65.21', 'A41.9', 'I46.9', 'J96.00', 'J80', 'Z51.11', 'R06.03'
              )
            )
            OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I21')
            OR (
              icd_version = 9 AND icd_code IN (
                '995.92', '785.52', '038.9', '427.5', '518.81', '518.82', 'V58.11', '786.03'
              )
            )
            OR (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410')
          THEN icd_code
        END
      ) AS critical_illness_count,
      MAX(
        CASE
          WHEN
            (icd_version = 10 AND (SUBSTR(icd_code, 1, 3) = 'I21' OR icd_code = 'I46.9'))
            OR (icd_version = 9 AND (SUBSTR(icd_code, 1, 3) = '410' OR icd_code = '427.5'))
          THEN 1
          ELSE 0
        END
      ) AS has_cardiac_complication,
      MAX(
        CASE
          WHEN
            (icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'I60' AND 'I69')
            OR (icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '430' AND '438')
          THEN 1
          ELSE 0
        END
      ) AS has_neuro_complication
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  cohort_with_scores AS (
    SELECT
      ab.*,
      dx.has_cardiac_complication,
      dx.has_neuro_complication,
      (dx.diagnosis_count + (dx.critical_illness_count * 5)) AS comorbidity_score
    FROM
      admissions_base AS ab
      INNER JOIN diagnoses_agg AS dx
        ON ab.hadm_id = dx.hadm_id
    WHERE
      dx.has_pe = 1
  ),
  high_comorbidity_cohort AS (
    SELECT
      *
    FROM
      cohort_with_scores
    WHERE
      comorbidity_score > (
        SELECT
          APPROX_QUANTILES(comorbidity_score, 100)[OFFSET(75)]
        FROM
          cohort_with_scores
      )
  ),
  risk_calculation AS (
    SELECT
      *,
      (
        0.6 * (
          (age_at_admission - MIN(age_at_admission) OVER ()) / NULLIF(
            (MAX(age_at_admission) OVER () - MIN(age_at_admission) OVER ()), 0
          )
        ) + 0.4 * (
          (comorbidity_score - MIN(comorbidity_score) OVER ()) / NULLIF(
            (MAX(comorbidity_score) OVER () - MIN(comorbidity_score) OVER ()), 0
          )
        )
      ) * 100 AS composite_risk_score
    FROM
      high_comorbidity_cohort
  ),
  final_data_with_ranks AS (
    SELECT
      *,
      PERCENT_RANK() OVER (
        ORDER BY
          composite_risk_score
      ) AS percentile_rank,
      CASE
        WHEN
          hospital_expire_flag = 1
          OR (
            dod IS NOT NULL AND DATETIME_DIFF(dod, dischtime, DAY) BETWEEN 0 AND 30
          )
        THEN 1
        ELSE 0
      END AS is_deceased_30_day,
      CASE
        WHEN dod IS NOT NULL
        THEN DATETIME_DIFF(dod, admittime, DAY)
        ELSE NULL
      END AS survival_days_from_admission
    FROM
      risk_calculation
  )
SELECT
  ROUND(
    AVG(
      IF(age_at_admission = 84, percentile_rank, NULL)
    ) * 100, 2
  ) AS percentile_rank_for_84_yo,
  ROUND(AVG(is_deceased_30_day) * 100, 2) AS mortality_rate_30_day_perc,
  ROUND(AVG(has_cardiac_complication) * 100, 2) AS cardiac_complication_rate_perc,
  ROUND(AVG(has_neuro_complication) * 100, 2) AS neuro_complication_rate_perc,
  (
    SELECT
      ROUND(APPROX_QUANTILES(survival_days_from_admission, 2)[OFFSET(1)], 1)
    FROM
      final_data_with_ranks
    WHERE
      survival_days_from_admission IS NOT NULL
  ) AS median_survival_days_for_deceased
FROM
  final_data_with_ranks;
