WITH
  cohort_stays AS (
    SELECT
      i.subject_id,
      i.hadm_id,
      i.stay_id,
      i.intime,
      i.outtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS i
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON i.subject_id = p.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON i.hadm_id = a.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        p.anchor_age + DATETIME_DIFF(i.intime, DATETIME(p.anchor_year, 1, 1, 0, 0, 0), YEAR)
      ) BETWEEN 55 AND 65
      AND i.hadm_id IN (
        SELECT DISTINCT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          icd_code LIKE '4275%'
          OR icd_code LIKE 'I46%'
      )
  ),

  vitals_first_24h AS (
    SELECT
      cs.stay_id,
      ce.itemid,
      ce.valuenum
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN cohort_stays AS cs
      ON ce.stay_id = cs.stay_id
    WHERE
      ce.charttime >= cs.intime AND ce.charttime <= DATETIME_ADD(cs.intime, INTERVAL 24 HOUR)
      AND ce.itemid IN (
        220045,
        220179,
        220052,
        220210,
        220277
      )
      AND ce.valuenum IS NOT NULL
  ),

  instability_scores AS (
    SELECT
      stay_id,
      SAFE_DIVIDE(
        SUM(
          CASE
            WHEN itemid = 220045 AND (valuenum < 50 OR valuenum > 120) THEN 1
            WHEN itemid = 220179 AND (valuenum < 90 OR valuenum > 180) THEN 1
            WHEN itemid = 220052 AND valuenum < 65 THEN 1
            WHEN itemid = 220210 AND (valuenum < 8 OR valuenum > 25) THEN 1
            WHEN itemid = 220277 AND valuenum < 90 THEN 1
            ELSE 0
          END
        ),
        COUNT(*)
      ) * 100 AS instability_score
    FROM
      vitals_first_24h
    GROUP BY
      stay_id
    HAVING
      COUNT(*) >= 10
  ),

  ranked_cohort AS (
    SELECT
      sc.stay_id,
      cs.hospital_expire_flag,
      SAFE_DIVIDE(DATETIME_DIFF(cs.outtime, cs.intime, HOUR), 24.0) AS icu_los_days,
      sc.instability_score,
      NTILE(10) OVER (ORDER BY sc.instability_score DESC) AS instability_decile
    FROM
      instability_scores AS sc
    INNER JOIN cohort_stays AS cs
      ON sc.stay_id = cs.stay_id
  )

SELECT
  (
    SELECT
      SAFE_DIVIDE(COUNTIF(instability_score < 70), COUNT(*)) * 100
    FROM ranked_cohort
  ) AS percentile_rank_of_score_70,
  (
    SELECT
      AVG(icu_los_days)
    FROM ranked_cohort
    WHERE
      instability_decile = 1
  ) AS avg_icu_los_days_top_decile,
  (
    SELECT
      AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100
    FROM ranked_cohort
    WHERE
      instability_decile = 1
  ) AS mortality_rate_pct_top_decile,
  (
    SELECT
      COUNT(*)
    FROM ranked_cohort
    WHERE
      instability_decile = 1
  ) AS patient_count_top_decile,
  (
    SELECT
      COUNT(*)
    FROM ranked_cohort
  ) AS total_patients_in_analyzed_cohort;
