WITH
  hhs_cohort_ids AS (
    SELECT
      adm.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON adm.subject_id = pat.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS diag ON adm.hadm_id = diag.hadm_id
    WHERE
      pat.gender = 'F'
      AND (
        DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age
      ) BETWEEN 68 AND 78
      AND (
        diag.icd_code LIKE '2502%'
        OR diag.icd_code LIKE 'E100%'
        OR diag.icd_code LIKE 'E110%'
        OR diag.icd_code LIKE 'E130%'
      )
    GROUP BY
      adm.hadm_id
  ),
  patient_base AS (
    SELECT
      adm.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS los_days,
      CASE
        WHEN adm.hadm_id IN (
          SELECT
            hadm_id
          FROM
            hhs_cohort_ids
        ) THEN TRUE
        ELSE FALSE
      END AS is_target_cohort
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
  ),
  patient_med_summary AS (
    SELECT
      pb.hadm_id,
      COUNT(DISTINCT pres.drug) AS complexity_score,
      CASE
        WHEN COUNT(DISTINCT CASE
          WHEN LOWER(pres.drug) LIKE '%pril%'
          OR LOWER(pres.drug) LIKE '%sartan%' THEN 'ace_arb'
          WHEN LOWER(pres.drug) LIKE '%spironolactone%'
          OR LOWER(pres.drug) LIKE '%amiloride%'
          OR LOWER(pres.drug) LIKE '%triamterene%'
          OR LOWER(pres.drug) LIKE '%eplerenone%' THEN 'k_sparing_diuretic'
          WHEN LOWER(pres.drug) LIKE '%potassium chloride%'
          OR LOWER(pres.drug) LIKE 'kcl%'
          OR LOWER(pres.drug) LIKE '%k-dur%'
          OR LOWER(pres.drug) LIKE '%klor-con%' THEN 'k_supplement'
          WHEN LOWER(pres.drug) LIKE '%ibuprofen%'
          OR LOWER(pres.drug) LIKE '%naproxen%'
          OR LOWER(pres.drug) LIKE '%ketorolac%'
          OR LOWER(pres.drug) LIKE '%diclofenac%'
          OR LOWER(pres.drug) LIKE '%indomethacin%' THEN 'nsaid'
          ELSE NULL
        END) >= 2 THEN 1
        ELSE 0
      END AS has_hyperk_interaction_risk
    FROM
      patient_base AS pb
      LEFT JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pres ON pb.hadm_id = pres.hadm_id
      AND pres.starttime BETWEEN pb.admittime AND DATETIME_ADD(pb.admittime, INTERVAL 72 HOUR)
    GROUP BY
      pb.hadm_id
  ),
  patient_ranked_data AS (
    SELECT
      pb.hadm_id,
      pb.is_target_cohort,
      pb.los_days,
      pb.hospital_expire_flag,
      COALESCE(ms.complexity_score, 0) AS complexity_score,
      COALESCE(ms.has_hyperk_interaction_risk, 0) AS has_hyperk_interaction_risk,
      PERCENT_RANK() OVER (
        PARTITION BY
          pb.is_target_cohort
        ORDER BY
          COALESCE(ms.complexity_score, 0)
      ) AS complexity_percentile_rank,
      NTILE(4) OVER (
        PARTITION BY
          pb.is_target_cohort
        ORDER BY
          COALESCE(ms.complexity_score, 0)
      ) AS complexity_quartile
    FROM
      patient_base AS pb
      LEFT JOIN patient_med_summary AS ms ON pb.hadm_id = ms.hadm_id
  )
SELECT
  CASE
    WHEN is_target_cohort THEN 'Target Cohort (Female, 68-78, HHS)'
    ELSE 'General Inpatient Population'
  END AS patient_group,
  COUNT(hadm_id) AS total_patients,
  AVG(complexity_score) AS avg_med_complexity_score_72hr,
  APPROX_QUANTILES(complexity_score, 4) AS complexity_score_distribution,
  APPROX_QUANTILES(
    IF
      (has_hyperk_interaction_risk = 1, complexity_percentile_rank, NULL), 2
  ) [OFFSET (1)] AS median_percentile_rank_of_risk_patients,
  AVG(has_hyperk_interaction_risk) * 100 AS percent_with_hyperk_risk_interaction,
  AVG(
    CASE
      WHEN complexity_quartile = 4 THEN los_days
    END
  ) AS top_quartile_avg_los_days,
  AVG(
    CASE
      WHEN complexity_quartile = 4 THEN hospital_expire_flag
    END
  ) * 100 AS top_quartile_mortality_rate_percent
FROM
  patient_ranked_data
GROUP BY
  is_target_cohort
ORDER BY
  is_target_cohort DESC;
