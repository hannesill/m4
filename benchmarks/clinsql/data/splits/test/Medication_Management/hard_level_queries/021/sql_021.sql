WITH
  cohort_base AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 41 AND 51
  ),
  neutropenic_fever_hadms AS (
    SELECT
      cb.subject_id,
      cb.hadm_id,
      cb.admittime,
      cb.dischtime,
      cb.hospital_expire_flag
    FROM
      cohort_base AS cb
    WHERE
      cb.hadm_id IN (
        SELECT
          hadm_id
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        GROUP BY
          hadm_id
        HAVING
          COUNT(
            DISTINCT CASE
              WHEN icd_code LIKE 'D70%' OR icd_code LIKE '288.0%' THEN 'neutropenia'
            END
          ) > 0
          AND COUNT(
            DISTINCT CASE
              WHEN icd_code LIKE 'R50%' OR icd_code LIKE '780.6%' THEN 'fever'
            END
          ) > 0
      )
  ),
  medication_complexity AS (
    SELECT
      nf.hadm_id,
      COUNT(DISTINCT LOWER(pr.drug)) AS complexity_score
    FROM
      neutropenic_fever_hadms AS nf
      JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr ON nf.hadm_id = pr.hadm_id
    WHERE
      pr.starttime BETWEEN nf.admittime AND TIMESTAMP_ADD(nf.admittime, INTERVAL 48 HOUR)
    GROUP BY
      nf.hadm_id
  ),
  readmission_data AS (
    SELECT
      hadm_id,
      CASE
        WHEN next_admittime IS NOT NULL AND TIMESTAMP_DIFF(next_admittime, dischtime, DAY) <= 30 THEN 1
        ELSE 0
      END AS is_readmitted_30d
    FROM
      (
        SELECT
          a.hadm_id,
          a.dischtime,
          LEAD(a.admittime, 1) OVER (
            PARTITION BY
              a.subject_id
            ORDER BY
              a.admittime
          ) AS next_admittime
        FROM
          `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        WHERE
          a.subject_id IN (
            SELECT DISTINCT subject_id FROM neutropenic_fever_hadms
          )
      )
  ),
  final_cohort_data AS (
    SELECT
      nf.hadm_id,
      nf.hospital_expire_flag,
      TIMESTAMP_DIFF(nf.dischtime, nf.admittime, DAY) AS los_days,
      COALESCE(mc.complexity_score, 0) AS complexity_score,
      rd.is_readmitted_30d,
      NTILE(3) OVER (
        ORDER BY
          COALESCE(mc.complexity_score, 0)
      ) AS complexity_tertile
    FROM
      neutropenic_fever_hadms AS nf
      LEFT JOIN medication_complexity AS mc ON nf.hadm_id = mc.hadm_id
      LEFT JOIN readmission_data AS rd ON nf.hadm_id = rd.hadm_id
  )
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS num_patients_in_stratum,
  MIN(complexity_score) AS min_complexity_score,
  MAX(complexity_score) AS max_complexity_score,
  ROUND(AVG(complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(CAST(is_readmitted_30d AS FLOAT64)) * 100, 2) AS readmission_rate_30d_pct
FROM
  final_cohort_data
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
