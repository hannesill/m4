WITH hemorrhagic_stroke_cohort AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    i.stay_id,
    i.intime,
    i.outtime,
    a.hospital_expire_flag,
    DATETIME_DIFF(i.outtime, i.intime, HOUR) AS icu_los_hours
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS i
    ON a.hadm_id = i.hadm_id
  WHERE
    p.gender = 'M'
    AND (p.anchor_age + EXTRACT(YEAR FROM i.intime) - p.anchor_year) BETWEEN 74 AND 84
    AND i.hadm_id IN (
      SELECT DISTINCT
        hadm_id
      FROM
        `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
      WHERE
        (icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432'))
        OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62'))
    )
),
hourly_vitals AS (
  SELECT
    ce.stay_id,
    DATETIME_TRUNC(ce.charttime, HOUR) AS chart_hour,
    AVG(CASE WHEN ce.itemid IN (646, 220277) THEN ce.valuenum ELSE NULL END) AS spo2,
    AVG(
      CASE
        WHEN ce.itemid IN (223762, 676) THEN ce.valuenum
        WHEN ce.itemid IN (223761, 678, 679) THEN (ce.valuenum - 32) * 5 / 9
        ELSE NULL
      END
    ) AS temp_c,
    AVG(CASE WHEN ce.itemid IN (618, 615, 220210, 224690) THEN ce.valuenum ELSE NULL END) AS resp_rate
  FROM
    `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
  INNER JOIN
    hemorrhagic_stroke_cohort AS cohort
    ON ce.stay_id = cohort.stay_id
  WHERE
    ce.charttime BETWEEN cohort.intime AND DATETIME_ADD(cohort.intime, INTERVAL 48 HOUR)
    AND ce.itemid IN (
      646, 220277,
      223762, 676,
      223761, 678, 679,
      618, 615, 220210, 224690
    )
    AND ce.valuenum IS NOT NULL
  GROUP BY
    ce.stay_id,
    chart_hour
),
hourly_abnormal_flags AS (
  SELECT
    stay_id,
    chart_hour,
    CASE WHEN spo2 < 90 THEN 1 ELSE 0 END AS hypoxemia_hour,
    CASE WHEN temp_c > 38.5 THEN 1 ELSE 0 END AS fever_hour,
    CASE WHEN resp_rate > 20 THEN 1 ELSE 0 END AS tachypnea_hour
  FROM
    hourly_vitals
  WHERE
    spo2 IS NOT NULL OR temp_c IS NOT NULL OR resp_rate IS NOT NULL
),
patient_instability_scores AS (
  SELECT
    cohort.stay_id,
    cohort.icu_los_hours,
    cohort.hospital_expire_flag,
    COALESCE(SUM(CASE WHEN flags.hypoxemia_hour = 1 OR flags.fever_hour = 1 OR flags.tachypnea_hour = 1 THEN 1 ELSE 0 END), 0) AS instability_score,
    COALESCE(SUM(flags.hypoxemia_hour), 0) AS total_hypoxemia_hours,
    COALESCE(SUM(flags.fever_hour), 0) AS total_fever_hours,
    COALESCE(SUM(flags.tachypnea_hour), 0) AS total_tachypnea_hours
  FROM
    hemorrhagic_stroke_cohort AS cohort
  LEFT JOIN
    hourly_abnormal_flags AS flags
    ON cohort.stay_id = flags.stay_id
  GROUP BY
    cohort.stay_id,
    cohort.icu_los_hours,
    cohort.hospital_expire_flag
),
ranked_patients AS (
  SELECT
    *,
    NTILE(10) OVER (ORDER BY instability_score DESC, stay_id) AS instability_decile
  FROM
    patient_instability_scores
),
cohort_percentiles AS (
  SELECT
    APPROX_QUANTILES(instability_score, 100)[OFFSET(90)] AS p90_instability_score
  FROM
    patient_instability_scores
)
SELECT
  p.p90_instability_score AS cohort_wide_90th_percentile_score,
  'Top_10_Percent_Unstable' AS risk_group,
  COUNT(r.stay_id) AS num_patients,
  AVG(r.icu_los_hours) AS avg_icu_los_hours,
  AVG(CAST(r.hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent,
  AVG(r.instability_score) AS avg_instability_score,
  AVG(r.total_fever_hours) AS avg_fever_hours,
  AVG(r.total_hypoxemia_hours) AS avg_hypoxemia_hours,
  AVG(r.total_tachypnea_hours) AS avg_tachypnea_hours
FROM
  ranked_patients AS r,
  cohort_percentiles AS p
WHERE
  r.instability_decile = 1
GROUP BY
  p.p90_instability_score
UNION ALL
SELECT
  p.p90_instability_score AS cohort_wide_90th_percentile_score,
  'Condition_Matched_Cohort_All' AS risk_group,
  COUNT(r.stay_id) AS num_patients,
  AVG(r.icu_los_hours) AS avg_icu_los_hours,
  AVG(CAST(r.hospital_expire_flag AS FLOAT64)) * 100 AS mortality_rate_percent,
  AVG(r.instability_score) AS avg_instability_score,
  AVG(r.total_fever_hours) AS avg_fever_hours,
  AVG(r.total_hypoxemia_hours) AS avg_hypoxemia_hours,
  AVG(r.total_tachypnea_hours) AS avg_tachypnea_hours
FROM
  ranked_patients AS r,
  cohort_percentiles AS p
GROUP BY
  p.p90_instability_score;
