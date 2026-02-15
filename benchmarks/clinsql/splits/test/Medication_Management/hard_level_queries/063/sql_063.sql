WITH
  pneumonia_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        d.icd_code LIKE '48%'
        OR d.icd_code LIKE 'J12%'
        OR d.icd_code LIKE 'J13%'
        OR d.icd_code LIKE 'J14%'
        OR d.icd_code LIKE 'J15%'
        OR d.icd_code LIKE 'J16%'
        OR d.icd_code LIKE 'J17%'
        OR d.icd_code LIKE 'J18%'
      )
      AND (DATETIME_DIFF(a.admittime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR) + p.anchor_age) BETWEEN 48 AND 58
    GROUP BY
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      age_at_admission
  ),
  icu_admissions AS (
    SELECT DISTINCT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays`
  ),
  medications_24hr AS (
    SELECT
      pa.hadm_id,
      pr.drug,
      CASE
        WHEN LOWER(pr.drug) LIKE '%fluoxetine%'
        OR LOWER(pr.drug) LIKE '%sertraline%'
        OR LOWER(pr.drug) LIKE '%citalopram%'
        OR LOWER(pr.drug) LIKE '%escitalopram%'
        OR LOWER(pr.drug) LIKE '%paroxetine%'
        OR LOWER(pr.drug) LIKE '%venlafaxine%'
        OR LOWER(pr.drug) LIKE '%duloxetine%'
        OR LOWER(pr.drug) LIKE '%amitriptyline%'
        OR LOWER(pr.drug) LIKE '%nortriptyline%'
        OR LOWER(pr.drug) LIKE '%tramadol%'
        OR LOWER(pr.drug) LIKE '%fentanyl%'
        OR LOWER(pr.drug) LIKE '%ondansetron%'
        OR LOWER(pr.drug) LIKE '%linezolid%'
        OR LOWER(pr.drug) LIKE '%mirtazapine%'
        OR LOWER(pr.drug) LIKE '%buspirone%' THEN 1
        ELSE 0
      END AS is_serotonergic
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      INNER JOIN pneumonia_admissions AS pa ON pr.hadm_id = pa.hadm_id
    WHERE
      pr.starttime BETWEEN pa.admittime AND TIMESTAMP_ADD(pa.admittime, INTERVAL 24 HOUR)
  ),
  patient_level_scores AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT drug) AS med_complexity_score,
      CASE
        WHEN COUNT(DISTINCT CASE WHEN is_serotonergic = 1 THEN drug END) >= 2 THEN 1
        ELSE 0
      END AS has_serotonergic_interaction_risk
    FROM
      medications_24hr
    GROUP BY
      hadm_id
  ),
  categorized_and_ranked AS (
    SELECT
      pa.hadm_id,
      pa.hospital_expire_flag,
      DATETIME_DIFF(pa.dischtime, pa.admittime, DAY) AS los_days,
      COALESCE(pls.med_complexity_score, 0) AS med_complexity_score,
      CASE
        WHEN COALESCE(pls.has_serotonergic_interaction_risk, 0) = 1 THEN '1_Serotonergic_Interaction_Risk'
        WHEN icu.hadm_id IS NOT NULL THEN '2_ICU_Patient_No_Interaction'
        ELSE '3_Baseline_Non_ICU'
      END AS patient_group,
      PERCENT_RANK() OVER (
        PARTITION BY
          CASE
            WHEN COALESCE(pls.has_serotonergic_interaction_risk, 0) = 1 THEN '1_Serotonergic_Interaction_Risk'
            WHEN icu.hadm_id IS NOT NULL THEN '2_ICU_Patient_No_Interaction'
            ELSE '3_Baseline_Non_ICU'
          END
        ORDER BY
          COALESCE(pls.med_complexity_score, 0)
      ) AS complexity_percentile_rank
    FROM
      pneumonia_admissions AS pa
      LEFT JOIN patient_level_scores AS pls ON pa.hadm_id = pls.hadm_id
      LEFT JOIN icu_admissions AS icu ON pa.hadm_id = icu.hadm_id
  )
SELECT
  patient_group,
  COUNT(hadm_id) AS total_patients,
  ROUND(AVG(med_complexity_score), 2) AS avg_med_complexity,
  APPROX_QUANTILES(med_complexity_score, 100)[OFFSET(25)] AS p25_med_complexity,
  APPROX_QUANTILES(med_complexity_score, 100)[OFFSET(50)] AS p50_med_complexity,
  APPROX_QUANTILES(med_complexity_score, 100)[OFFSET(75)] AS p75_med_complexity,
  ROUND(AVG(los_days), 2) AS avg_los_days_overall,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_overall_pct,
  COUNTIF(complexity_percentile_rank >= 0.75) AS patients_in_top_quartile,
  ROUND(AVG(IF(complexity_percentile_rank >= 0.75, los_days, NULL)), 2) AS avg_los_top_quartile,
  ROUND(AVG(IF(complexity_percentile_rank >= 0.75, CAST(hospital_expire_flag AS FLOAT64), NULL)) * 100, 2) AS mortality_rate_top_quartile_pct
FROM
  categorized_and_ranked
GROUP BY
  patient_group
ORDER BY
  patient_group;
