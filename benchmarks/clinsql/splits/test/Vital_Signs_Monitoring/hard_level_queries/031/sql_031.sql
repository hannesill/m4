WITH
-- Step 1: Identify all hospital admissions that are postoperative by checking the patient's service.
postop_hadm AS (
  SELECT DISTINCT hadm_id
  FROM `physionet-data.mimiciv_3_1_hosp.services`
  WHERE LOWER(curr_service) LIKE '%surg%' -- Catches SURG, CSURG, NSURG, TSURG, VSURG etc.
),

-- Step 2: Rank ICU stays within each hospital admission to identify the first one.
-- This CTE corrects the error in the original query.
ranked_icustays AS (
  SELECT
    icu.subject_id,
    icu.hadm_id,
    icu.stay_id,
    icu.intime,
    icu.outtime,
    -- Rank stays by their admission time. rn=1 is the first stay for a given hadm_id.
    ROW_NUMBER() OVER(PARTITION BY icu.hadm_id ORDER BY icu.intime) AS rn
  FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  -- Pre-filter for only postoperative hospital admissions to improve performance.
  WHERE icu.hadm_id IN (SELECT hadm_id FROM postop_hadm)
),

-- Step 3: Create a base cohort of the first ICU stay for each postoperative hospital admission.
-- Calculate patient age at ICU admission and ICU length of stay.
icustay_details AS (
  SELECT
    p.subject_id,
    p.gender,
    a.hadm_id,
    a.hospital_expire_flag,
    icu.stay_id,
    icu.intime,
    -- Calculate age at ICU admission.
    EXTRACT(YEAR FROM icu.intime) - p.anchor_year + p.anchor_age AS age_at_icu_intime,
    -- Calculate ICU LOS in days
    DATETIME_DIFF(icu.outtime, icu.intime, HOUR) / 24.0 AS icu_los_days
  FROM ranked_icustays AS icu
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON icu.hadm_id = a.hadm_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON icu.subject_id = p.subject_id
  -- CRITICAL FIX: Filter for only the first ICU stay (rn=1) per hospital admission.
  WHERE
    icu.rn = 1
),

-- Step 4: Define the 'Target' and 'Comparison' cohorts based on demographics.
cohorts AS (
  SELECT
    stay_id,
    intime,
    icu_los_days,
    hospital_expire_flag,
    CASE
      WHEN gender = 'M' AND age_at_icu_intime BETWEEN 63 AND 73 THEN 'Target'
      ELSE 'Comparison'
    END AS cohort_group
  FROM icustay_details
),

-- Step 5: Extract relevant vital signs from chartevents for our cohorts within the first 72 hours.
vitals_raw AS (
  SELECT
    c.stay_id,
    c.charttime,
    -- Temperature: Unify Fahrenheit and Celsius to Celsius
    CASE
      WHEN c.itemid = 223761 THEN (c.valuenum - 32) * 5 / 9 -- Fahrenheit to Celsius
      WHEN c.itemid = 223762 THEN c.valuenum               -- Already Celsius
    END AS temperature_c,
    -- SpO2
    CASE WHEN c.itemid = 220277 THEN c.valuenum END AS spo2,
    -- Respiratory Rate
    CASE WHEN c.itemid = 220210 THEN c.valuenum END AS resp_rate
  FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS c
  INNER JOIN cohorts AS coh
    ON c.stay_id = coh.stay_id
  WHERE
    c.itemid IN (
      223761, -- Temperature Fahrenheit
      223762, -- Temperature Celsius
      220277, -- O2 saturation pulseoxymetry
      220210  -- Respiratory Rate
    )
    -- Filter for the first 72 hours of the ICU stay.
    AND c.charttime BETWEEN coh.intime AND DATETIME_ADD(coh.intime, INTERVAL 72 HOUR)
    AND c.valuenum IS NOT NULL
),

-- Step 6: Pivot the data to have one row per measurement time, and clean outliers.
vitals_cleaned AS (
  SELECT
    stay_id,
    charttime,
    MAX(CASE WHEN temperature_c > 25 AND temperature_c < 45 THEN temperature_c ELSE NULL END) AS temperature_c,
    MAX(CASE WHEN spo2 > 50 AND spo2 <= 100 THEN spo2 ELSE NULL END) AS spo2,
    MAX(CASE WHEN resp_rate > 0 AND resp_rate < 60 THEN resp_rate ELSE NULL END) AS resp_rate
  FROM vitals_raw
  GROUP BY stay_id, charttime
),

-- Step 7: For each patient stay, calculate variability (Standard Deviation) and count of abnormal episodes.
vitals_agg_by_stay AS (
  SELECT
    stay_id,
    -- Variability metrics
    STDDEV_SAMP(temperature_c) AS stddev_temp,
    STDDEV_SAMP(spo2) AS stddev_spo2,
    STDDEV_SAMP(resp_rate) AS stddev_rr,
    -- Abnormal episode counts
    COUNTIF(temperature_c > 38.5) AS fever_episodes,
    COUNTIF(spo2 < 90) AS hypoxemia_episodes,
    COUNTIF(resp_rate > 20) AS tachypnea_episodes
  FROM vitals_cleaned
  GROUP BY stay_id
  -- Ensure there are enough measurements to calculate a meaningful standard deviation.
  HAVING COUNT(temperature_c) > 5 AND COUNT(spo2) > 5 AND COUNT(resp_rate) > 5
),

-- Step 8: Calculate population-level normalization factors (mean and stddev of the variability metrics).
normalization_factors AS (
  SELECT
    AVG(stddev_temp) AS avg_std_temp,
    STDDEV(stddev_temp) AS std_std_temp,
    AVG(stddev_spo2) AS avg_std_spo2,
    STDDEV(stddev_spo2) AS std_std_spo2,
    AVG(stddev_rr) AS avg_std_rr,
    STDDEV(stddev_rr) AS std_std_rr
  FROM vitals_agg_by_stay
),

-- Step 9: Calculate a composite instability score for each patient and determine their instability quartile.
ranked_patients AS (
  SELECT
    coh.stay_id,
    coh.cohort_group,
    coh.icu_los_days,
    coh.hospital_expire_flag,
    agg.fever_episodes,
    agg.hypoxemia_episodes,
    agg.tachypnea_episodes,
    -- The instability score is the sum of the Z-scores of each vital's standard deviation.
    (
      SAFE_DIVIDE(agg.stddev_temp - norm.avg_std_temp, norm.std_std_temp) +
      SAFE_DIVIDE(agg.stddev_spo2 - norm.avg_std_spo2, norm.std_std_spo2) +
      SAFE_DIVIDE(agg.stddev_rr - norm.avg_std_rr, norm.std_std_rr)
    ) AS instability_score,
    -- Use NTILE to rank patients into quartiles based on their instability score.
    NTILE(4) OVER (PARTITION BY coh.cohort_group ORDER BY
      (
        SAFE_DIVIDE(agg.stddev_temp - norm.avg_std_temp, norm.std_std_temp) +
        SAFE_DIVIDE(agg.stddev_spo2 - norm.avg_std_spo2, norm.std_std_spo2) +
        SAFE_DIVIDE(agg.stddev_rr - norm.avg_std_rr, norm.std_std_rr)
      ) DESC
    ) AS instability_quartile
  FROM cohorts AS coh
  INNER JOIN vitals_agg_by_stay AS agg
    ON coh.stay_id = agg.stay_id
  CROSS JOIN normalization_factors AS norm
),

-- Step 10: Create final summary aggregates for the groups to be compared.
group_summaries AS (
  SELECT
    'Target Group (Most Unstable Quartile)' AS group_name,
    1 AS sort_order,
    COUNT(stay_id) AS patient_count,
    AVG(instability_score) AS avg_instability_score,
    AVG(fever_episodes) AS avg_fever_episodes,
    AVG(hypoxemia_episodes) AS avg_hypoxemia_episodes,
    AVG(tachypnea_episodes) AS avg_tachypnea_episodes,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS INT64)) * 100 AS mortality_rate_percent
  FROM ranked_patients
  WHERE cohort_group = 'Target' AND instability_quartile = 1
  GROUP BY group_name, sort_order

  UNION ALL

  SELECT
    'Comparison Group (Other Post-Op Patients)' AS group_name,
    2 AS sort_order,
    COUNT(stay_id) AS patient_count,
    AVG(instability_score) AS avg_instability_score,
    AVG(fever_episodes) AS avg_fever_episodes,
    AVG(hypoxemia_episodes) AS avg_hypoxemia_episodes,
    AVG(tachypnea_episodes) AS avg_tachypnea_episodes,
    AVG(icu_los_days) AS avg_icu_los_days,
    AVG(CAST(hospital_expire_flag AS INT64)) * 100 AS mortality_rate_percent
  FROM ranked_patients
  WHERE cohort_group = 'Comparison'
  GROUP BY group_name, sort_order
)

-- Final Step: Present the comparison table and include the 95th percentile score for the target group.
SELECT
  gs.group_name,
  gs.patient_count,
  ROUND(gs.avg_instability_score, 2) AS avg_instability_score,
  -- Calculate and display the 95th percentile instability score, showing it only on the target group's row.
  CASE
    WHEN gs.sort_order = 1
    THEN ROUND((SELECT (APPROX_QUANTILES(instability_score, 100))[OFFSET(95)] FROM ranked_patients WHERE cohort_group = 'Target'), 2)
    ELSE NULL
  END AS target_group_95th_percentile_score,
  ROUND(gs.avg_fever_episodes, 2) AS avg_fever_episodes_72h,
  ROUND(gs.avg_hypoxemia_episodes, 2) AS avg_hypoxemia_episodes_72h,
  ROUND(gs.avg_tachypnea_episodes, 2) AS avg_tachypnea_episodes_72h,
  ROUND(gs.avg_icu_los_days, 2) AS avg_icu_los_days,
  ROUND(gs.mortality_rate_percent, 2) AS in_hospital_mortality_percent
FROM group_summaries AS gs
ORDER BY gs.sort_order;
