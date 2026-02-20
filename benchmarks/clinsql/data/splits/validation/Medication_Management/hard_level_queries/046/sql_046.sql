WITH
  cohort_base AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
  ),
  multi_trauma_admissions AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (
        icd_code LIKE 'S%'
        OR icd_code LIKE 'T%'
        OR (
          icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '800' AND '999'
        )
      )
    GROUP BY
      hadm_id
    HAVING
      COUNT(DISTINCT icd_code) >= 2
  ),
  target_cohort AS (
    SELECT
      cb.subject_id,
      cb.hadm_id,
      cb.admittime,
      cb.dischtime,
      cb.hospital_expire_flag
    FROM
      cohort_base AS cb
      INNER JOIN multi_trauma_admissions AS mta ON cb.hadm_id = mta.hadm_id
    WHERE
      cb.age_at_admission BETWEEN 45 AND 55
  ),
  readmission_flags AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(
          LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime),
          dischtime,
          DAY
        ) <= 30 THEN 1
        ELSE 0
      END AS readmitted_30_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  medication_complexity AS (
    SELECT
      rx.hadm_id,
      (
        COUNT(DISTINCT rx.drug) * 1
      ) + (
        COUNT(DISTINCT rx.route) * 2
      ) + (
        COUNT(DISTINCT CASE WHEN LOWER(rx.route) = 'iv' THEN rx.drug END) * 3
      ) AS medication_complexity_score
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      INNER JOIN target_cohort AS tc ON rx.hadm_id = tc.hadm_id
    WHERE
      rx.starttime <= DATETIME_ADD(tc.admittime, INTERVAL 7 DAY)
      AND rx.drug IS NOT NULL
    GROUP BY
      rx.hadm_id
  ),
  cohort_with_scores_and_outcomes AS (
    SELECT
      tc.hadm_id,
      COALESCE(mc.medication_complexity_score, 0) AS medication_complexity_score,
      DATETIME_DIFF(tc.dischtime, tc.admittime, DAY) AS los_days,
      tc.hospital_expire_flag,
      rf.readmitted_30_days,
      NTILE(3) OVER (
        ORDER BY
          COALESCE(mc.medication_complexity_score, 0)
      ) AS complexity_tertile
    FROM
      target_cohort AS tc
      LEFT JOIN medication_complexity AS mc ON tc.hadm_id = mc.hadm_id
      LEFT JOIN readmission_flags AS rf ON tc.hadm_id = rf.hadm_id
  )
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS num_admissions,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  MIN(medication_complexity_score) AS min_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(readmitted_30_days) * 100, 2) AS readmission_30day_rate_percent
FROM
  cohort_with_scores_and_outcomes
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
