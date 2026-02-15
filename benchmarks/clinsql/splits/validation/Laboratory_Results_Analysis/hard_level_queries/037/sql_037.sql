WITH
  hemorrhagic_stroke_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 70 AND 80
      AND (
        d.icd_code LIKE '430%'
        OR d.icd_code LIKE '431%'
        OR d.icd_code LIKE '432%'
        OR d.icd_code LIKE 'I60%'
        OR d.icd_code LIKE 'I61%'
        OR d.icd_code LIKE 'I62%'
      )
    GROUP BY
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
  ),
  critical_lab_definitions AS (
    SELECT 50983 AS itemid, 'Sodium' AS lab_name, 120 AS critical_low, 160 AS critical_high UNION ALL
    SELECT 50971, 'Potassium', 2.5, 6.5 UNION ALL
    SELECT 50912, 'Creatinine', NULL, 4.0 UNION ALL
    SELECT 51301, 'WBC', 2.0, 30.0 UNION ALL
    SELECT 51265, 'Platelet Count', 20.0, NULL UNION ALL
    SELECT 50931, 'Glucose', 40.0, 400.0 UNION ALL
    SELECT 50813, 'Lactate', NULL, 4.0 UNION ALL
    SELECT 50820, 'pH', 7.2, 7.6
  ),
  all_labs_first_48h AS (
    SELECT
      le.hadm_id,
      le.itemid,
      le.valuenum
    FROM
      `physionet-data.mimiciv_3_1_hosp.labevents` AS le
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON le.hadm_id = a.hadm_id
    WHERE
      le.valuenum IS NOT NULL
      AND DATETIME_DIFF(le.charttime, a.admittime, HOUR) BETWEEN 0 AND 48
  ),
  critical_events AS (
    SELECT
      l.hadm_id,
      l.itemid,
      c.lab_name
    FROM
      all_labs_first_48h AS l
      INNER JOIN critical_lab_definitions AS c
        ON l.itemid = c.itemid
    WHERE
      (l.valuenum < c.critical_low) OR (l.valuenum > c.critical_high)
  ),
  instability_scores AS (
    SELECT
      cohort.hadm_id,
      cohort.admittime,
      cohort.dischtime,
      cohort.hospital_expire_flag,
      COUNT(ce.itemid) AS instability_score
    FROM
      hemorrhagic_stroke_cohort AS cohort
      LEFT JOIN critical_events AS ce
        ON cohort.hadm_id = ce.hadm_id
    GROUP BY
      cohort.hadm_id,
      cohort.admittime,
      cohort.dischtime,
      cohort.hospital_expire_flag
  )
SELECT
  (
    SELECT APPROX_QUANTILES(instability_score, 100)[OFFSET(25)]
    FROM instability_scores
  ) AS cohort_p25_instability_score,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM critical_events WHERE hadm_id IN (SELECT hadm_id FROM hemorrhagic_stroke_cohort)),
    (SELECT COUNT(*) FROM hemorrhagic_stroke_cohort)
  ) AS cohort_critical_events_per_admission,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM critical_events),
    (SELECT COUNT(DISTINCT hadm_id) FROM all_labs_first_48h)
  ) AS general_population_critical_events_per_admission,
  (
    SELECT AVG(DATETIME_DIFF(dischtime, admittime, DAY))
    FROM instability_scores
  ) AS cohort_avg_los_days,
  (
    SELECT AVG(hospital_expire_flag)
    FROM instability_scores
  ) AS cohort_mortality_rate;
