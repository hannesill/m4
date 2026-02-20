WITH
  icd_trauma_stays AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_version = 9
        AND SUBSTR(icd_code, 1, 3) BETWEEN '800' AND '959'
      )
      OR (
        icd_version = 10
        AND SUBSTR(icd_code, 1, 1) IN ('S', 'T')
      )
    GROUP BY
      hadm_id
    HAVING
      COUNT(DISTINCT icd_code) >= 3
  ),
  icu_stays_ranked AS (
    SELECT
      stay_id,
      hadm_id,
      subject_id,
      intime,
      outtime,
      ROW_NUMBER() OVER (PARTITION BY hadm_id ORDER BY intime ASC) AS stay_rank
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays`
  ),
  cohort_stays AS (
    SELECT
      icu.stay_id,
      icu.hadm_id,
      icu.intime,
      icu.outtime,
      adm.hospital_expire_flag,
      DATETIME_DIFF(icu.outtime, icu.intime, HOUR) AS icu_los_hours
    FROM
      icu_stays_ranked AS icu
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat ON icu.subject_id = pat.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
    INNER JOIN
      icd_trauma_stays AS trauma ON icu.hadm_id = trauma.hadm_id
    WHERE
      icu.stay_rank = 1
      AND pat.gender = 'M'
      AND (DATETIME_DIFF(icu.intime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age) BETWEEN 68 AND 78
  ),
  vitals_raw AS (
    SELECT
      ch.stay_id,
      ch.charttime,
      CASE WHEN ch.itemid = 220045 THEN ch.valuenum ELSE NULL END AS heart_rate,
      CASE WHEN ch.itemid IN (220052, 220181, 225312) THEN ch.valuenum ELSE NULL END AS map,
      CASE WHEN ch.itemid IN (220210, 224690) THEN ch.valuenum ELSE NULL END AS resp_rate
    FROM
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ch
    INNER JOIN
      cohort_stays AS cohort ON ch.stay_id = cohort.stay_id
    WHERE
      ch.charttime BETWEEN cohort.intime AND DATETIME_ADD(cohort.intime, INTERVAL 24 HOUR)
      AND ch.itemid IN (
        220045,
        220052,
        220181,
        225312,
        220210,
        224690
      )
      AND ch.valuenum IS NOT NULL
      AND ch.valuenum > 0
  ),
  vitals_hourly AS (
    SELECT
      stay_id,
      DATETIME_TRUNC(charttime, HOUR) AS hour_bucket,
      AVG(heart_rate) AS avg_hr,
      AVG(map) AS avg_map,
      AVG(resp_rate) AS avg_rr
    FROM
      vitals_raw
    GROUP BY
      stay_id,
      hour_bucket
  ),
  instability_scores AS (
    SELECT
      stay_id,
      SUM(
        (
          CASE WHEN avg_hr > 100 THEN 1 ELSE 0 END
        ) + (
          CASE WHEN avg_map < 65 THEN 1 ELSE 0 END
        ) + (
          CASE WHEN avg_rr > 20 THEN 1 ELSE 0 END
        )
      ) AS instability_score,
      SUM(CASE WHEN avg_hr > 100 THEN 1 ELSE 0 END) AS tachycardia_episodes,
      SUM(CASE WHEN avg_map < 65 THEN 1 ELSE 0 END) AS hypotension_episodes,
      SUM(CASE WHEN avg_rr > 20 THEN 1 ELSE 0 END) AS tachypnea_episodes
    FROM
      vitals_hourly
    GROUP BY
      stay_id
  ),
  ranked_patients AS (
    SELECT
      cs.stay_id,
      cs.icu_los_hours,
      cs.hospital_expire_flag,
      sc.instability_score,
      sc.tachycardia_episodes,
      sc.hypotension_episodes,
      sc.tachypnea_episodes,
      NTILE(4) OVER (
        ORDER BY
          sc.instability_score
      ) AS instability_quartile,
      NTILE(10) OVER (
        ORDER BY
          sc.instability_score
      ) AS instability_decile
    FROM
      cohort_stays AS cs
    LEFT JOIN
      instability_scores AS sc ON cs.stay_id = sc.stay_id
  ),
  quartile_summary AS (
    SELECT
      CAST(instability_quartile AS STRING) AS strata,
      COUNT(stay_id) AS num_patients,
      AVG(instability_score) AS avg_instability_score,
      AVG(icu_los_hours) AS avg_icu_los_hours,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate,
      NULL AS avg_tachycardia_episodes,
      NULL AS avg_hypotension_episodes,
      NULL AS avg_tachypnea_episodes
    FROM
      ranked_patients
    GROUP BY
      instability_quartile
  ),
  top_decile_summary AS (
    SELECT
      'Top Decile (10)' AS strata,
      COUNT(stay_id) AS num_patients,
      AVG(instability_score) AS avg_instability_score,
      AVG(icu_los_hours) AS avg_icu_los_hours,
      AVG(CAST(hospital_expire_flag AS FLOAT64)) AS mortality_rate,
      AVG(tachycardia_episodes) AS avg_tachycardia_episodes,
      AVG(hypotension_episodes) AS avg_hypotension_episodes,
      AVG(tachypnea_episodes) AS avg_tachypnea_episodes
    FROM
      ranked_patients
    WHERE
      instability_decile = 10
  )
SELECT
  *
FROM
  quartile_summary
UNION ALL
SELECT
  *
FROM
  top_decile_summary
ORDER BY
  strata
