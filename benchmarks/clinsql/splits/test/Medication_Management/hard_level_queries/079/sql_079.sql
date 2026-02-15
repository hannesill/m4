WITH
  cohort_admissions AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p ON a.subject_id = p.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        EXTRACT(
          YEAR
          FROM
            a.admittime
        ) - p.anchor_year + p.anchor_age
      ) BETWEEN 89 AND 99
      AND (
        d.icd_code LIKE '430%'
        OR d.icd_code LIKE '431%'
        OR d.icd_code LIKE '432%'
        OR d.icd_code LIKE 'I60%'
        OR d.icd_code LIKE 'I61%'
        OR d.icd_code LIKE 'I62%'
      )
    GROUP BY
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
  ),
  med_complexity AS (
    SELECT
      c.hadm_id,
      COUNT(DISTINCT pr.drug) AS medication_complexity_score
    FROM
      cohort_admissions AS c
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr ON c.hadm_id = pr.hadm_id
    WHERE
      pr.starttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 7 DAY)
    GROUP BY
      c.hadm_id
  ),
  readmission_flags AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(next_admittime, dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS readmitted_30_days_flag
    FROM
      (
        SELECT
          hadm_id,
          subject_id,
          dischtime,
          LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
        FROM
          `physionet-data.mimiciv_3_1_hosp.admissions`
      )
  ),
  cohort_outcomes AS (
    SELECT
      c.hadm_id,
      c.subject_id,
      COALESCE(mc.medication_complexity_score, 0) AS medication_complexity_score,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS los_days,
      c.hospital_expire_flag AS mortality_flag,
      COALESCE(rf.readmitted_30_days_flag, 0) AS readmitted_30_days_flag
    FROM
      cohort_admissions AS c
      LEFT JOIN med_complexity AS mc ON c.hadm_id = mc.hadm_id
      LEFT JOIN readmission_flags AS rf ON c.hadm_id = rf.hadm_id
  ),
  ranked_cohort AS (
    SELECT
      hadm_id,
      medication_complexity_score,
      los_days,
      mortality_flag,
      readmitted_30_days_flag,
      NTILE(5) OVER (
        ORDER BY
          medication_complexity_score
      ) AS complexity_quintile
    FROM
      cohort_outcomes
  )
SELECT
  complexity_quintile,
  COUNT(DISTINCT hadm_id) AS num_patients_in_stratum,
  MIN(medication_complexity_score) AS min_complexity_score_in_quintile,
  MAX(medication_complexity_score) AS max_complexity_score_in_quintile,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(mortality_flag), 3) AS mortality_rate,
  ROUND(AVG(readmitted_30_days_flag), 3) AS readmission_rate_30_day
FROM
  ranked_cohort
GROUP BY
  complexity_quintile
ORDER BY
  complexity_quintile;
