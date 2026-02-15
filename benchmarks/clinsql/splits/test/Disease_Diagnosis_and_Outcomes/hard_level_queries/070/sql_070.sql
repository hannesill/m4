WITH
  BaseCohort AS (
    SELECT
      p.subject_id,
      p.anchor_age,
      p.dod,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.deathtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 59 AND 69
  ),
  AdmissionDiagnoses AS (
    SELECT
      hadm_id,
      SUM(
        CASE
          WHEN icd_code IN ('R6881', 'R570', '99592', '78552') THEN 10
          WHEN icd_code IN ('R6521', 'A419', '0389') THEN 8
          WHEN STARTS_WITH(icd_code, 'I21') OR STARTS_WITH(icd_code, '410') OR icd_code IN ('I469', '4275') THEN 7
          WHEN icd_code IN ('J9600', 'J80', '51881', '51882') THEN 6
          WHEN icd_code IN ('Z5111', 'R0603', 'V5811', '78603') THEN 5
          WHEN STARTS_WITH(icd_code, 'I824') OR STARTS_WITH(icd_code, '4534') THEN 0
          ELSE 1
        END
      ) AS comorbidity_score,
      MAX(
        CASE
          WHEN STARTS_WITH(icd_code, 'I824') OR STARTS_WITH(icd_code, '4534') THEN 1
          ELSE 0
        END
      ) AS has_dvt,
      MAX(
        CASE
          WHEN
            icd_code IN ('R6881', 'R570', '99592', '78552', 'R6521', 'A419', '0389', 'J9600', 'J80', '51881', '51882', 'Z5111', 'R0603', 'V5811', '78603')
            OR STARTS_WITH(icd_code, 'I21') OR STARTS_WITH(icd_code, '410') OR icd_code IN ('I469', '4275')
            THEN 1
          ELSE 0
        END
      ) AS has_major_complication
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  EnrichedDVTAdmissions AS (
    SELECT
      bc.subject_id,
      bc.hadm_id,
      bc.anchor_age,
      ad.comorbidity_score,
      ad.has_major_complication,
      DATETIME_DIFF(bc.dischtime, bc.admittime, DAY) AS length_of_stay_days,
      CASE
        WHEN bc.deathtime IS NOT NULL AND bc.deathtime <= DATETIME_ADD(bc.admittime, INTERVAL 30 DAY) THEN 1
        WHEN bc.dod IS NOT NULL AND DATETIME(bc.dod) <= DATETIME_ADD(bc.admittime, INTERVAL 30 DAY) THEN 1
        ELSE 0
      END AS is_30_day_mortality,
      CASE
        WHEN bc.hospital_expire_flag = 1 THEN DATETIME_DIFF(bc.deathtime, bc.admittime, DAY)
        ELSE NULL
      END AS survival_days_if_deceased_in_hosp
    FROM
      BaseCohort AS bc
    JOIN
      AdmissionDiagnoses AS ad
      ON bc.hadm_id = ad.hadm_id
    WHERE
      ad.has_dvt = 1
  ),
  HighBurdenDVTCohort AS (
    SELECT
      *,
      PERCENTILE_CONT(comorbidity_score, 0.75) OVER () AS p75_comorbidity_score
    FROM
      EnrichedDVTAdmissions
  ),
  RiskScoredCohort AS (
    SELECT
      h.subject_id,
      h.hadm_id,
      h.is_30_day_mortality,
      h.has_major_complication,
      h.survival_days_if_deceased_in_hosp,
      (
        0.5 * SAFE_DIVIDE(
          h.comorbidity_score - MIN(h.comorbidity_score) OVER (),
          MAX(h.comorbidity_score) OVER () - MIN(h.comorbidity_score) OVER ()
        )
        + 0.3 * SAFE_DIVIDE(
          h.anchor_age - MIN(h.anchor_age) OVER (),
          MAX(h.anchor_age) OVER () - MIN(h.anchor_age) OVER ()
        )
        + 0.2 * SAFE_DIVIDE(
          h.length_of_stay_days - MIN(h.length_of_stay_days) OVER (),
          MAX(h.length_of_stay_days) OVER () - MIN(h.length_of_stay_days) OVER ()
        )
      ) AS composite_risk_score
    FROM
      HighBurdenDVTCohort AS h
    WHERE
      h.comorbidity_score > h.p75_comorbidity_score
      AND h.length_of_stay_days IS NOT NULL AND h.length_of_stay_days > 0
  )
SELECT
  'Female, 59-69, with DVT and High Comorbidity Burden (>75th Pct)' AS cohort_description,
  COUNT(DISTINCT subject_id) AS total_patients,
  ROUND(AVG(is_30_day_mortality) * 100, 2) AS mortality_rate_30_day_pct,
  ROUND(AVG(has_major_complication) * 100, 2) AS major_complication_rate_pct,
  APPROX_QUANTILES(survival_days_if_deceased_in_hosp, 100 IGNORE NULLS)[OFFSET(50)] AS median_survival_days_for_deceased,
  ROUND(APPROX_QUANTILES(composite_risk_score, 100 IGNORE NULLS)[OFFSET(25)], 4) AS risk_score_25th_percentile,
  ROUND(APPROX_QUANTILES(composite_risk_score, 100 IGNORE NULLS)[OFFSET(50)], 4) AS risk_score_50th_percentile_median,
  ROUND(APPROX_QUANTILES(composite_risk_score, 100 IGNORE NULLS)[OFFSET(75)], 4) AS risk_score_75th_percentile
FROM
  RiskScoredCohort;
